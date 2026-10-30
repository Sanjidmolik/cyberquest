"""Reporting, warnings and moderator actions. Nothing here acts on its own: detection only
records that a warning was shown, and every restriction comes from a moderator with a reason."""

import json
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from cyberquest.ratelimit import is_rate_limited
from messaging import crypto
from messaging.models import Conversation, Message
from messaging.policy import Denied, RateLimited
from notifications.utils import notify

from .models import FlagEvent, ModerationLog, Report, Restriction

CONTEXT = 3                      # messages shown before and after the reported one
NOTE_MAX = 500
REPORT_RETENTION_DAYS = 180
FLAG_RETENTION_DAYS = 90
ACTIONS = {
    "dismiss": None,
    "warn": (Restriction.WARNING, None),
    "mute_24h": (Restriction.MUTE, timedelta(hours=24)),
    "mute_7d": (Restriction.MUTE, timedelta(days=7)),
    "suspend": (Restriction.SUSPENSION, None),
}


# ---------- automatic warnings (metadata only) ----------

def record_flag(user, kind):
    FlagEvent.objects.create(user=user, kind=kind)


def flag_counts(days=7, limit=20):
    """Per-user counts of warnings and sent-anyway messages: no text, no words."""
    since = timezone.now() - timedelta(days=days)
    rows = (FlagEvent.objects.filter(created_at__gte=since).values("user__username")
            .annotate(warned=Count("pk", filter=Q(kind=FlagEvent.WARNED)),
                      sent=Count("pk", filter=Q(kind=FlagEvent.SENT_ANYWAY)))
            .order_by("-sent", "-warned")[:limit])
    return [{"username": r["user__username"], "warned": r["warned"], "sent": r["sent"]} for r in rows]


# ---------- restrictions ----------

def active_restriction(user):
    return Restriction.objects.active().filter(user=user).order_by("-starts_at").first()


def restriction_reason(user):
    """Why this user can't send messages right now, or "" (used by messaging/policy.py)."""
    current = active_restriction(user)
    if current is None:
        return ""
    if current.kind == Restriction.SUSPENSION:
        return f"Your messaging is suspended: {current.reason}"
    until = timezone.localtime(current.ends_at)
    return f"Your messaging is muted until {until:%d %b, %H:%M}: {current.reason}"


def recent_warning(user, days=14):
    """The newest warning from a moderator in the last two weeks, for a banner in the inbox."""
    since = timezone.now() - timedelta(days=days)
    return Restriction.objects.filter(user=user, kind=Restriction.WARNING, starts_at__gte=since).first()


def notices(user):
    """The user's own warnings, mutes and suspensions, newest first."""
    now = timezone.now()
    rows = []
    for r in Restriction.objects.filter(user=user):
        active = r.kind != Restriction.WARNING and r.lifted_at is None and (r.ends_at is None or r.ends_at > now)
        rows.append({"kind": r.get_kind_display(), "reason": r.reason, "starts_at": r.starts_at,
                     "ends_at": r.ends_at, "lifted_at": r.lifted_at, "active": active,
                     "is_warning": r.kind == Restriction.WARNING})
    return rows


# ---------- reporting ----------

def _snapshot(message, photo_attached=False):
    """The reported message and up to CONTEXT messages either side, encrypted as one JSON blob."""
    conversation = message.conversation
    before = list(conversation.messages.filter(pk__lt=message.pk).order_by("-pk")[:CONTEXT])[::-1]
    after = list(conversation.messages.filter(pk__gt=message.pk).order_by("pk")[:CONTEXT])
    rows = []
    for m in before + [message] + after:
        if m.kind == Message.PHOTO:
            if m.pk == message.pk:
                text = ("[View-once photo: copy attached]" if photo_attached
                        else "[View-once photo: opened more than an hour ago, so no copy exists]")
            else:
                text = "[View-once photo]"
        else:
            text = "" if m.removed else m.text
        rows.append({
            "reported": m.pk == message.pk,
            "sender": m.sender.username if m.sender else "Deleted user",
            "text": text,
            "at": timezone.localtime(m.created_at).isoformat(),
        })
    return crypto.encrypt(json.dumps(rows, ensure_ascii=False))


def report(reporter, message_id, reason, note="", also_block=False):
    """Report a message you received. Returns (report, created). Reporting the same message
    twice does nothing the second time."""
    if reason not in dict(Report.REASONS):
        raise Denied("Choose a reason for the report.")
    note = (note or "").strip()
    if len(note) > NOTE_MAX:
        raise Denied(f"Keep the note under {NOTE_MAX} characters.")
    message = (Message.objects.select_related("conversation", "sender")
               .filter(pk=message_id, conversation__in=Conversation.objects.involving(reporter)).first())
    if message is None:
        raise Denied("Message not found.")
    if message.sender_id == reporter.pk:
        raise Denied("You can't report your own message.")
    if message.sender is None or message.removed:
        raise Denied("This message was removed and can't be reported.")
    if message.kind == Message.SYSTEM:
        raise Denied("Notices like this can't be reported.")
    existing = Report.objects.filter(message=message, reporter=reporter).first()
    if existing is not None:
        return existing, False
    if is_rate_limited(f"report:day:{reporter.pk}", limit=settings.MODERATION_REPORTS_PER_DAY, window_seconds=86_400):
        raise RateLimited("You've sent the maximum number of reports for today. Try again tomorrow.")
    from messaging.photos import copy_for_report, release_report_copy
    # A view-once photo: the unopened file, or the 1-hour copy kept after opening.
    photo, held = copy_for_report(message)
    try:
        with transaction.atomic():
            created = Report(
                message=message, reporter=reporter, reported_user=message.sender, reason=reason,
                note=crypto.encrypt(note) if note else "", snapshot=_snapshot(message, photo is not None),
            )
            if photo is not None:
                created.photo.save(photo.name, photo, save=False)
            created.save()
    except IntegrityError:            # a double click raced the first request
        if photo is not None and created.photo:
            created.photo.delete(save=False)
        return Report.objects.get(message=message, reporter=reporter), False
    release_report_copy(message, held)          # moved into the report: the held copy goes
    if also_block:
        from messaging.services import block
        block(reporter, message.sender)
    return created, True


# ---------- moderator side ----------

def _check_not_involved(moderator, report_obj):
    if moderator.pk in (report_obj.reporter_id, report_obj.reported_user_id):
        raise Denied("You can't handle a report you filed or one about you.")


def queue_for(moderator, status=Report.OPEN):
    """Reports this moderator may handle (never ones they filed or that are about them)."""
    return (Report.objects.filter(status=status).exclude(reporter=moderator).exclude(reported_user=moderator)
            .select_related("reporter", "reported_user"))


def reveal(moderator, report_obj):
    """Decrypt a report's message and context for a moderator. Logged every time."""
    _check_not_involved(moderator, report_obj)
    ModerationLog.objects.create(actor=moderator, subject=report_obj.reported_user, report=report_obj,
                                 action="view")
    rows = json.loads(crypto.decrypt(report_obj.snapshot)) if report_obj.snapshot else []
    note = crypto.decrypt(report_obj.note) if report_obj.note else ""
    return rows, note


def reported_photo(report_obj):
    """(bytes, content type) of a report's photo copy, or None. Only call right after reveal()
    (which checks the moderator and logs the view)."""
    if not report_obj.photo:
        return None
    from messaging.photos import content_type
    try:
        with report_obj.photo.storage.open(report_obj.photo.name, "rb") as handle:
            return crypto.decrypt_bytes(handle.read()), content_type(report_obj.photo.name)
    except Exception:  # noqa: BLE001 - shown as "couldn't be loaded"
        return None


def act(moderator, report_obj, action, reason):
    """Resolve a report: dismiss, warn, mute 24 h / 7 days, or suspend messaging."""
    _check_not_involved(moderator, report_obj)
    reason = (reason or "").strip()
    if action not in ACTIONS:
        raise Denied("Choose an action.")
    if not reason:
        raise Denied("Give a reason. It is logged, and shown to the user for warnings and mutes.")
    if report_obj.status != Report.OPEN:
        raise Denied("This report is already resolved.")
    subject = report_obj.reported_user
    now = timezone.now()
    with transaction.atomic():
        if ACTIONS[action] and subject is not None:
            kind, length = ACTIONS[action]
            Restriction.objects.create(user=subject, kind=kind, reason=reason, starts_at=now,
                                       ends_at=now + length if length else None,
                                       created_by=moderator, report=report_obj)
        Report.objects.filter(pk=report_obj.pk).update(status=Report.RESOLVED, resolution=action,
                                                       resolved_by=moderator, resolved_at=now)
        ModerationLog.objects.create(actor=moderator, subject=subject, report=report_obj, action=action,
                                     reason=reason)
    if ACTIONS[action] and subject is not None:
        label = dict(Restriction.KINDS)[ACTIONS[action][0]]
        notify(subject, f"{label}: {reason}"[:255], reverse("moderation_public:notices"))


def lift(moderator, restriction, reason):
    reason = (reason or "").strip()
    if restriction.user_id == moderator.pk:
        raise Denied("You can't lift a restriction on your own account.")
    if not reason:
        raise Denied("Give a reason for lifting it.")
    if restriction.lifted_at is not None:
        return
    Restriction.objects.filter(pk=restriction.pk).update(lifted_at=timezone.now())
    ModerationLog.objects.create(actor=moderator, subject=restriction.user, action="lift", reason=reason,
                                 report=restriction.report)
    notify(restriction.user, f"Your messaging restriction was lifted: {reason}"[:255],
           reverse("moderation_public:notices"))


# ---------- retention ----------

def purge_old(now=None, dry_run=False):
    """Delete resolved reports (and their snapshots) after 180 days, anonymising the log
    entries that pointed at them; delete warning metadata after 90 days."""
    now = now or timezone.now()
    old = Report.objects.filter(status=Report.RESOLVED, resolved_at__lt=now - timedelta(days=REPORT_RETENTION_DAYS))
    flags = FlagEvent.objects.filter(created_at__lt=now - timedelta(days=FLAG_RETENTION_DAYS))
    counts = {"reports": old.count(), "flags": flags.count()}
    if not dry_run:
        files = list(old.exclude(photo="").values_list("photo", flat=True))
        with transaction.atomic():
            ModerationLog.objects.filter(report__in=old).update(reason="", report=None)
            old.delete()
            flags.delete()
        storage = Report._meta.get_field("photo").storage
        for name in files:                   # reported photo copies go with their report
            try:
                storage.delete(name)
            except Exception:  # noqa: BLE001
                pass
    return counts


def export_for(user):
    """Moderation data for the user's own export: reports they filed (no message text),
    restrictions on their account, and warning metadata. Reports about them are left out so
    reporters stay anonymous."""
    filed = Report.objects.filter(reporter=user).order_by("created_at")
    return {
        "reports_filed": [{"reason": r.reason, "note": crypto.decrypt(r.note) if r.note else "",
                           "status": r.status, "created_at": r.created_at} for r in filed],
        "messaging_restrictions": [{"kind": r.kind, "reason": r.reason, "starts_at": r.starts_at,
                                    "ends_at": r.ends_at, "lifted_at": r.lifted_at}
                                   for r in Restriction.objects.filter(user=user).order_by("starts_at")],
        "message_warnings": [{"kind": f.kind, "at": f.created_at}
                             for f in FlagEvent.objects.filter(user=user).order_by("created_at")],
    }
