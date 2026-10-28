"""
Personal-data export and account deletion.

Exports are built in memory for the signed-in user and streamed straight to
them, so no export file is ever written to disk or kept on the server.

Never exported: password hashes, TOTP secrets or time steps, recovery-code
hashes, verification-code hashes, the session security stamp, or sessions.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import zipfile
from pathlib import PurePosixPath

from django.core.files.storage import default_storage
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

EXPORT_FORMAT_VERSION = 1

PROFILE_FIELDS = (
    "email", "username", "full_name", "date_of_birth", "cyber_class", "skill_level",
    "ethical_agreement", "course_intro_completed", "google_linked", "email_verified",
    "xp", "level", "current_streak", "longest_streak", "last_active_date",
    "date_joined", "last_login", "totp_enabled", "email_2fa_enabled",
)


def _rows(qs, fields):
    return [dict(zip(fields, values)) for values in qs.values_list(*fields)]


def build_export(user) -> dict:
    """Everything CyberQuest stores about this user that they can see or act on."""
    from achievements.models import UserBadge
    from certificates.models import IssuedCertificate
    from courses.models import CourseProgress, ReadingProgress
    from games.models import GameAttempt
    from notifications.models import Notification
    from pages.models import ContactMessage
    from practice.models import PracticeSession

    profile = {field: getattr(user, field) for field in PROFILE_FIELDS}
    profile["has_profile_picture"] = bool(user.profile_picture)
    profile["has_password"] = user.has_usable_password()

    attempts = _rows(
        GameAttempt.objects.filter(user=user).order_by("id"),
        ("id", "game_key", "status", "score", "total_questions", "xp_awarded",
         "started_at", "deadline_at", "completed_at", "elapsed_seconds",
         "time_remaining_seconds", "submission_method", "set_number", "answers"),
    )
    practice = _rows(
        PracticeSession.objects.filter(user=user).order_by("id"),
        ("id", "domain", "activity_type", "scenario_key", "difficulty", "score",
         "max_score", "status", "xp_awarded", "created_at", "completed_at",
         "result_summary", "strengths", "improvements", "decisions"),
    )
    courses = _rows(
        CourseProgress.objects.filter(user=user).order_by("completed_at"),
        ("course__code", "course__title", "completed_at"),
    )
    reading = _rows(
        ReadingProgress.objects.filter(user=user).order_by("updated_at"),
        ("course__code", "last_page_index", "updated_at"),
    )
    badges = _rows(
        UserBadge.objects.filter(user=user).order_by("earned_at"),
        ("badge__code", "badge__name", "earned_at"),
    )
    notifications = _rows(
        Notification.objects.filter(user=user).order_by("created_at"),
        ("message", "link_url", "is_read", "created_at"),
    )
    certificate = _rows(
        IssuedCertificate.objects.filter(user=user),
        ("certificate_id", "recipient_name", "score", "issued_at"),
    )
    contact = _rows(
        ContactMessage.objects.filter(email__iexact=user.email).order_by("submitted_at"),
        ("name", "email", "message", "submitted_at", "is_resolved"),
    )
    activity = [
        {"day": day} for day in user.activity_days.order_by("day").values_list("day", flat=True)
    ]

    return {
        "export": {
            "format_version": EXPORT_FORMAT_VERSION,
            "generated_at": timezone.now(),
            "service": "CyberQuest",
            "excluded": [
                "password hash", "authenticator secret", "recovery codes",
                "verification codes", "session data",
            ],
        },
        "profile": profile,
        "activity_days": activity,
        "mission_attempts": attempts,
        "practice_sessions": practice,
        "course_completions": courses,
        "reading_progress": reading,
        "badges": badges,
        "notifications": notifications,
        "certificate": certificate[0] if certificate else None,
        "contact_messages": contact,
        **_messaging_export(user),
    }


def _messaging_export(user) -> dict:
    from messaging.services import export_for
    return export_for(user)


def export_json_bytes(user) -> bytes:
    return json.dumps(build_export(user), cls=DjangoJSONEncoder, indent=2, ensure_ascii=False).encode("utf-8")


def _csv_bytes(rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, cls=DjangoJSONEncoder) if isinstance(value, (dict, list)) else value
                for key, value in row.items()
            })
    # A BOM lets spreadsheet apps detect UTF-8 (names may be non-ASCII).
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def export_zip_bytes(user) -> bytes:
    """One CSV per table, plus the profile picture when there is one."""
    data = build_export(user)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("profile.csv", _csv_bytes([data["profile"]]))
        for key in ("activity_days", "mission_attempts", "practice_sessions", "course_completions",
                    "reading_progress", "badges", "notifications", "contact_messages",
                    "messages", "blocked_members"):
            bundle.writestr(f"{key}.csv", _csv_bytes(data[key]))
        bundle.writestr("certificate.csv", _csv_bytes([data["certificate"]] if data["certificate"] else []))
        bundle.writestr("message_settings.csv", _csv_bytes([data["message_settings"]]))
        bundle.writestr("README.txt", (
            "CyberQuest personal data export\n"
            f"Generated: {data['export']['generated_at'].isoformat()}\n"
            "Not included: password hash, authenticator secret, recovery codes, "
            "verification codes, session data.\n"
        ))
        picture = user.profile_picture
        if picture:
            try:
                with picture.open("rb") as handle:
                    suffix = PurePosixPath(picture.name).suffix.lower() or ".img"
                    bundle.writestr(f"profile_picture{suffix}", handle.read())
            except (OSError, ValueError):
                logger.warning("Profile picture missing during export for user %s", user.pk)
    return archive.getvalue()


def _stored_file_names(user) -> list[str]:
    from certificates.models import IssuedCertificate

    names = []
    if user.profile_picture:
        names.append(user.profile_picture.name)
    cert = IssuedCertificate.objects.filter(user=user).only("pdf_file").first()
    if cert and cert.pdf_file:
        names.append(cert.pdf_file.name)
    return names


def _delete_files(names: list[str]) -> None:
    for name in names:
        try:
            if default_storage.exists(name):
                default_storage.delete(name)
        except OSError:
            # The account is already gone. Log the path for manual cleanup.
            logger.warning("Could not delete stored file %s after account deletion", name)


def delete_account(user) -> None:
    """Delete the user and every row that cascades from it, then their uploaded files.

    Cascades: activity days, recovery codes, verification codes, mission
    attempts, practice sessions, course and reading progress, badges,
    notifications, and the issued certificate. Question banks the user
    created as an administrator keep existing with no creator.
    Contact-form messages are support records and are not linked to the
    account; they are retained as described in the Privacy Policy.
    """
    names = _stored_file_names(user)
    user_id = user.pk
    with transaction.atomic():
        user.delete()
        transaction.on_commit(lambda: _delete_files(names))
    logger.info("Account %s deleted at the owner's request", user_id)
