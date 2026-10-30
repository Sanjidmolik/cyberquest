"""Deleting expired messages (and their photo files) for good.

Expired messages are already invisible (the default manager hides them), so this only frees
storage; how late it runs never affects what anyone can see. Two ways in:

- `purge(...)`: `manage.py purge_expired_messages` (host scheduler, every minute if possible)
  and the daily `purge_expired_data` backstop. Works through everything in batches.
- `maybe_sweep()`: called from the messaging and polling endpoints. At most once a minute
  across all workers, one request at a time (cache lock), one small batch, never raises.

Logs counts only: never message text, ids or usernames.
"""

import logging

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from .models import Message

logger = logging.getLogger("messaging.expiry")

SWEEP_BATCH = 200            # rows per in-request sweep: small enough not to slow a student
COMMAND_BATCH = 500
SWEEP_EVERY_KEY, SWEEP_EVERY_SECONDS = "messaging:sweep:recent", 60
SWEEP_LOCK_KEY, SWEEP_LOCK_SECONDS = "messaging:sweep:lock", 300


def _delete_files(names_and_storages):
    deleted = 0
    for storage, name in names_and_storages:
        try:
            storage.delete(name)
            deleted += 1
        except Exception:  # noqa: BLE001 - a missing file is fine; the row is what matters
            logger.warning("could not delete an expired photo file")
    return deleted


def purge_batch(limit, now=None, dry_run=False):
    """Delete up to `limit` expired messages, plus any opened view-once photo files still stored
    (a safety net: opening deletes them). Returns {"messages": n, "photo_files": n}."""
    now = now or timezone.now()
    rows = list(Message.all_objects.filter(expires_at__lte=now).order_by("pk")
                .values_list("pk", "photo", "report_copy")[:limit])
    if dry_run:
        return {"messages": len(rows), "photo_files": sum(bool(p) + bool(c) for _, p, c in rows)}
    from .photos import purge_opened_files
    opened = purge_opened_files(now=now, limit=limit)
    if not rows:
        return {"messages": 0, "photo_files": opened}
    storage = Message._meta.get_field("photo").storage
    files = [(storage, name) for _, photo, copy in rows for name in (photo, copy) if name]
    with transaction.atomic():
        Message.all_objects.filter(pk__in=[pk for pk, _, _ in rows], expires_at__lte=now).delete()
    return {"messages": len(rows), "photo_files": _delete_files(files) + opened}


def purge(now=None, dry_run=False, batch=COMMAND_BATCH):
    """Everything expired, batch by batch. Idempotent: a second run finds nothing."""
    now = now or timezone.now()
    total = {"messages": 0, "photo_files": 0}
    while True:
        done = purge_batch(batch, now=now, dry_run=dry_run)
        for key in total:
            total[key] += done[key]
        if dry_run or done["messages"] < batch:
            break
    if not dry_run and any(total.values()):
        logger.info("purged %d expired messages and %d photo files", total["messages"], total["photo_files"])
    return total


def maybe_sweep():
    """A small cleanup from inside a request, at most once a minute, one request at a time."""
    if not cache.add(SWEEP_EVERY_KEY, 1, SWEEP_EVERY_SECONDS):
        return None
    if not cache.add(SWEEP_LOCK_KEY, 1, SWEEP_LOCK_SECONDS):
        return None
    try:
        done = purge_batch(SWEEP_BATCH)
        if any(done.values()):
            logger.info("sweep purged %d expired messages and %d photo files", done["messages"], done["photo_files"])
        return done
    except Exception:  # noqa: BLE001 - cleanup must never break a student's request
        logger.warning("messaging sweep failed", exc_info=True)
        return None
    finally:
        cache.delete(SWEEP_LOCK_KEY)
