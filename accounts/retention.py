"""
Retention periods and the cleanup that enforces them.

The Privacy Policy renders RETENTION, and ``manage.py purge_expired_data``
applies the automated rows, so the published periods and the cleanup cannot
drift apart. Every step only removes data that is already expired or
abandoned, and running it twice in a row removes nothing the second time.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

VERIFICATION_CODE_GRACE_DAYS = 7
UNVERIFIED_SIGNUP_DAYS = 30
PREVIEW_ATTEMPT_DAYS = 7

# (record, how long it is kept, how it is removed)
RETENTION = [
    ("Account profile and learning records (XP, streaks, badges, mission attempts, practice, "
     "course progress, notifications, certificate)",
     "While your account exists",
     "Deleted when you delete your account"),
    ("Profile picture",
     "Until you replace or remove it, or delete your account",
     "File deleted from storage"),
    ("Email verification, sign-in and password-reset codes (stored only as a keyed hash)",
     f"Valid for 10 minutes; records kept {VERIFICATION_CODE_GRACE_DAYS} days after expiry for abuse investigation",
     "Automatic cleanup"),
    ("Unfinished sign-ups whose email was never verified",
     f"{UNVERIFIED_SIGNUP_DAYS} days",
     "Automatic cleanup"),
    ("Sign-in sessions",
     "Until you sign out or the session expires",
     "Expired sessions removed by automatic cleanup"),
    ("Rate-limit and security counters (contain an IP address or account number)",
     "15 minutes to 1 hour",
     "Expired entries removed by automatic cleanup"),
    ("Mission attempts left unfinished",
     "Closed automatically when the mission timer ends",
     "Kept as part of your attempt history"),
    ("Messages you send and receive (text encrypted when stored; not end-to-end)",
     "While your account exists",
     "When you delete your account, your messages stay in the other person's conversation as "
     "\"Deleted user\" with the text removed"),
    ("Message settings and the members you blocked",
     "While your account exists",
     "Deleted when you delete your account"),
    ("Reports you file about a message, with a copy of that message and up to three messages "
     "before and after it",
     "Until a moderator resolves it, then 180 days",
     "Automatic cleanup"),
    ("Moderation log (who took which action, and who opened reported content, and when)",
     "Kept; after 180 days the reason text and the link to the report are removed",
     "If you delete your account, entries stay with your name removed"),
    ("Warnings and messaging restrictions a moderator placed on your account",
     "While your account exists",
     "Deleted when you delete your account"),
    ("“This message may be offensive” warnings shown to you (when, and whether you sent "
     "anyway; never the message)",
     "90 days",
     "Automatic cleanup"),
    ("Practice Studio preview runs by staff (never count toward XP, badges or progress)",
     f"{PREVIEW_ATTEMPT_DAYS} days",
     "Automatic cleanup"),
    ("Data exports",
     "Not stored; generated when you ask and sent straight to your browser",
     "Nothing to remove"),
    ("Contact-form messages",
     "Until an administrator deletes them; they are not linked to your account",
     "Ask through the contact page to have yours removed"),
    ("Hosting backups and provider logs",
     "According to the hosting provider's backup and log schedule",
     "Expire on the provider's schedule; deleted data may remain in a backup until it expires"),
]


def purge_verification_codes(now=None, dry_run=False) -> int:
    from accounts.models import VerificationCode

    now = now or timezone.now()
    cutoff = now - timedelta(days=VERIFICATION_CODE_GRACE_DAYS)
    qs = VerificationCode.objects.filter(expires_at__lt=cutoff)
    count = qs.count()
    if not dry_run and count:
        qs.delete()
    return count


def purge_unverified_signups(now=None, dry_run=False) -> int:
    """Remove abandoned password sign-ups that never proved ownership of the email."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    now = now or timezone.now()
    cutoff = now - timedelta(days=UNVERIFIED_SIGNUP_DAYS)
    qs = User.objects.filter(
        email_verified=False,
        is_active=False,
        is_staff=False,
        is_superuser=False,
        last_login__isnull=True,
        date_joined__lt=cutoff,
        xp=0,
    )
    count = qs.count()
    if not dry_run and count:
        from accounts.privacy import delete_account

        for user in qs.iterator():
            delete_account(user)
    return count


def purge_expired_sessions(now=None, dry_run=False) -> int:
    from django.contrib.sessions.models import Session

    now = now or timezone.now()
    qs = Session.objects.filter(expire_date__lt=now)
    count = qs.count()
    if not dry_run and count:
        qs.delete()
    return count


def purge_expired_cache(now=None, dry_run=False) -> int:
    """Delete expired rows from the database cache table used for rate limits."""
    from django.conf import settings
    from django.db import connection

    cache_conf = settings.CACHES.get("default", {})
    if cache_conf.get("BACKEND") != "django.core.cache.backends.db.DatabaseCache":
        return 0
    table = connection.ops.quote_name(cache_conf["LOCATION"])
    now = (now or timezone.now()).replace(microsecond=0)
    # Same adaptation Django's DatabaseCache uses when it writes `expires`.
    now = connection.ops.adapt_datetimefield_value(now)
    with connection.cursor() as cursor:
        if dry_run:
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE expires < %s", [now])
            return int(cursor.fetchone()[0])
        cursor.execute(f"DELETE FROM {table} WHERE expires < %s", [now])
        return cursor.rowcount or 0


def purge_preview_attempts(now=None, dry_run=False) -> int:
    """Remove staff preview runs from the Practice Studio (and their answers)."""
    from practice.models import Attempt

    cutoff = (now or timezone.now()) - timedelta(days=PREVIEW_ATTEMPT_DAYS)
    qs = Attempt.objects.filter(is_preview=True, started_at__lt=cutoff)
    count = qs.count()
    if not dry_run and count:
        qs.delete()
    return count


def close_expired_attempts(dry_run=False) -> int:
    from games.attempts import finalize_expired_attempts
    from games.models import GameAttempt

    if dry_run:
        return GameAttempt.objects.filter(
            status=GameAttempt.STATUS_IN_PROGRESS, deadline_at__lte=timezone.now(),
        ).count()
    total = 0
    while True:
        closed = finalize_expired_attempts(limit=200)
        total += closed
        if closed < 200:
            return total


def _moderation_purge(dry_run) -> dict:
    from moderation.services import purge_old
    counts = purge_old(dry_run=dry_run)
    return {"resolved_reports_older_than_180_days": counts["reports"],
            "message_warnings_older_than_90_days": counts["flags"]}


def _expired_messages_purge(dry_run) -> dict:
    """Backstop for disappearing messages (normally cleaned every minute)."""
    from messaging.expiry import purge
    counts = purge(dry_run=dry_run)
    return {"expired_disappearing_messages": counts["messages"], "expired_message_photo_files": counts["photo_files"]}


def run_all(dry_run=False) -> dict:
    return {
        "verification_codes": purge_verification_codes(dry_run=dry_run),
        "unverified_signups": purge_unverified_signups(dry_run=dry_run),
        "expired_sessions": purge_expired_sessions(dry_run=dry_run),
        "expired_cache_entries": purge_expired_cache(dry_run=dry_run),
        "expired_mission_attempts_closed": close_expired_attempts(dry_run=dry_run),
        "old_practice_preview_runs": purge_preview_attempts(dry_run=dry_run),
        **_moderation_purge(dry_run),
        **_expired_messages_purge(dry_run),
    }
