"""View-once photos: the only media type in messages.

- Upload: JPEG, PNG or WebP up to 5 MB, checked with Pillow, re-encoded so EXIF and other
  metadata are gone (cyberquest/images.py), resized to at most 1600 px wide, encrypted with
  the message keys (Fernet) and saved under a random name in private storage
  (messaging/storage.py). Accepted conversations only, rate limited per day.
- Open: the recipient only, once. A single conditional UPDATE (photo_opened_at IS NULL) picks
  the one request that wins; only that request reads the file, deletes it and gets the bytes.
  Every other request gets "already opened". The sender can't open it at all.
- Report copy: the winner also re-saves the (still encrypted) bytes under a separate name in
  `report_copy`, kept for REPORT_HOLD (1 hour). Nothing serves that field: only the recipient's
  report moves it into the report. Cleanup deletes it when the hour is up.
- Nothing is ever served from a URL of its own: the bytes go back in the opening response,
  with Cache-Control: no-store.
"""

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from cyberquest.images import FORMATS, clean_image, encode, resized
from cyberquest.ratelimit import is_rate_limited

from . import crypto, events, policy
from .models import REPORT_HOLD, Conversation, Message, expiry_for
from .policy import Denied, RateLimited

logger = logging.getLogger("messaging.photos")

MAX_WIDTH = 1600
VIEW_SECONDS = 10                 # the viewer's countdown (client side)
CONTENT_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


class AlreadyOpened(Denied):
    """The photo was opened before (view once)."""


def _storage():
    return Message._meta.get_field("photo").storage


def content_type(name):
    parts = (name or "").rsplit("/", 1)[-1].split(".")
    return CONTENT_TYPES.get(parts[1] if len(parts) > 2 else "", "application/octet-stream")


def _check_can_send_photo(sender, conversation):
    policy.check_send(sender, conversation)
    if conversation.state != Conversation.ACCEPTED:
        raise Denied("Photos can be sent once the other person has accepted your message request.")
    if is_rate_limited(f"msg:photo:day:{sender.pk}", limit=settings.MESSAGING_PHOTOS_PER_DAY, window_seconds=86_400):
        raise RateLimited("You've sent the maximum number of photos for today. Try again tomorrow.")


def send_photo(sender, conversation, upload):
    """Store an encrypted view-once photo message. Raises Denied / RateLimited."""
    _check_can_send_photo(sender, conversation)
    if upload is None:
        raise Denied("Choose a photo first.")
    try:
        clean, fmt = clean_image(upload)
    except ValidationError as exc:
        raise Denied(exc.messages[0])
    policy.check_message_rate(sender)
    ext, out_fmt = FORMATS[fmt]
    token = crypto.encrypt_bytes(encode(resized(clean, MAX_WIDTH), out_fmt))
    timer = Conversation.objects.filter(pk=conversation.pk).values_list("disappear_after", flat=True).first()
    now = timezone.now()
    message = Message(conversation=conversation, sender=sender, kind=Message.PHOTO, created_at=now,
                      timer=timer, expires_at=expiry_for(timer, now))
    message.set_text("")
    with transaction.atomic():
        message.photo.save(f"{uuid.uuid4().hex}.{ext}.bin", ContentFile(token), save=False)
        message.save()
        Conversation.objects.filter(pk=conversation.pk).update(last_message_at=now)
    from .services import _mark_read
    _mark_read(conversation, sender, message.pk)
    transaction.on_commit(lambda: events.conversation_changed(conversation, message.pk))
    return message


def open_photo(viewer, conversation, message_id):
    """Return (bytes, content type) to the recipient exactly once, then delete the file.

    Raises Message.DoesNotExist (not a visible photo here), Denied (the sender, or a block),
    or AlreadyOpened."""
    message = Message.objects.get(pk=message_id, conversation=conversation, kind=Message.PHOTO)
    if message.sender_id == viewer.pk:
        raise Denied("You can't reopen a view-once photo you sent.")
    other = conversation.other(viewer)
    if other is None or policy.blocked_between(viewer, other):
        raise Denied("This photo isn't available.")
    won = (Message.objects.filter(pk=message.pk, photo_opened_at__isnull=True).exclude(photo="")
           .update(photo_opened_at=timezone.now()))
    if not won:
        raise AlreadyOpened("This photo was already opened.")
    name = message.photo.name
    token = data = None
    try:
        with _storage().open(name, "rb") as handle:
            token = handle.read()
        data = crypto.decrypt_bytes(token)
    except Exception:  # noqa: BLE001 - a missing or unreadable file is "already gone"
        logger.warning("a view-once photo could not be read")
    finally:
        hold, until = "", None
        if data is not None:                 # the reportable copy: same ciphertext, new private name
            try:
                hold = _storage().save(f"msg-report-hold/{uuid.uuid4().hex}.{name.split('.')[-2]}.bin",
                                       ContentFile(token))
                until = timezone.now() + REPORT_HOLD
            except Exception:  # noqa: BLE001 - no copy is better than a failed open
                logger.warning("a report copy could not be kept")
        try:
            _storage().delete(name)
        except Exception:  # noqa: BLE001 - the cleanup job retries
            logger.warning("a view-once photo file could not be deleted yet")
        Message.all_objects.filter(pk=message.pk).update(photo="", report_copy=hold, report_copy_until=until)
    transaction.on_commit(lambda: events.conversation_changed(conversation))
    if data is None:
        raise AlreadyOpened("This photo isn't available any more.")
    return data, content_type(name)


def photo_state(message):
    return "opened" if message.photo_opened_at else "view_once"


def preview(message, viewer):
    if message.photo_opened_at:
        return "Photo · opened"
    return "Photo · sent" if message.sender_id == viewer.pk else "Photo · view once"


def copy_for_report(message, now=None):
    """(encrypted copy for the report, held file to remove afterwards or "") for a reported photo:
    the unopened photo itself, or the 1-hour report copy of an opened one. (None, "") if neither."""
    if message.kind != Message.PHOTO:
        return None, ""
    now = now or timezone.now()
    if message.photo and not message.photo_opened_at:
        source, held = message.photo.name, ""
    elif message.report_copy and message.report_copy_until and message.report_copy_until > now:
        source = held = message.report_copy.name
    else:
        return None, ""
    try:
        with _storage().open(source, "rb") as handle:
            return ContentFile(handle.read(), name=f"{uuid.uuid4().hex}.{source.split('.')[-2]}.bin"), held
    except Exception:  # noqa: BLE001
        logger.warning("a reported photo could not be copied")
        return None, ""


def release_report_copy(message, held):
    """The report now has its own copy: delete the held one (it is never needed again)."""
    if not held:
        return
    try:
        _storage().delete(held)
    except Exception:  # noqa: BLE001 - the cleanup job deletes it when the hour is up
        logger.warning("a report copy could not be deleted yet")
        return
    Message.all_objects.filter(pk=message.pk, report_copy=held).update(report_copy="", report_copy_until=None)


def purge_opened_files(now=None, limit=200):
    """Report copies whose hour is up, and (a safety net) files of photos opened more than
    VIEW_SECONDS ago that are still stored. Returns how many files were deleted."""
    now = now or timezone.now()
    cutoff = now - timedelta(seconds=VIEW_SECONDS)
    deleted = 0
    leftovers = list(Message.all_objects.filter(photo_opened_at__lt=cutoff).exclude(photo="")
                     .values_list("pk", "photo")[:limit])
    for pk, name in leftovers:
        try:
            _storage().delete(name)
        except Exception:  # noqa: BLE001
            logger.warning("an opened photo file could not be deleted yet")
            continue
        Message.all_objects.filter(pk=pk).update(photo="")
        deleted += 1
    held = list(Message.all_objects.filter(report_copy_until__lte=now).exclude(report_copy="")
                .values_list("pk", "report_copy")[:limit])
    for pk, name in held:
        try:
            _storage().delete(name)
        except Exception:  # noqa: BLE001
            logger.warning("a report copy could not be deleted yet")
            continue
        Message.all_objects.filter(pk=pk).update(report_copy="", report_copy_until=None)
        deleted += 1
    return deleted
