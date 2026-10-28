"""The one rule set `load_scenarios` and `convert_scenarios` use to write seed content.

A deploy runs both commands (build.sh), so they must never undo work done in the
Practice Studio. For each seed scenario:

  - missing            -> created (source "seed")
  - source "studio"    -> skipped: someone edited it in the studio
  - published versions -> skipped: the studio has published it at least once
  - hand-edited        -> skipped: its content no longer matches the hash the seed last wrote
  - otherwise          -> updated when the seed changed, left alone when not

`force` is a set of slugs the operator named explicitly; only those rows are overwritten
despite the rules above (and the overwrite is written to the studio audit log).
"""

import hashlib
import json
import logging

from django.db import transaction

from .models import Scenario, ScenarioVersion, StudioAuditLog

logger = logging.getLogger("practice.seeding")

SEED_FIELDS = ("kind", "title", "difficulty", "est_minutes", "time_limit_sec", "xp_reward")


def content_hash(content):
    """A stable fingerprint of scenario content (key order and whitespace don't matter)."""
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def snapshot_seed(row):
    """Keep a copy of the content the seed just wrote, so attempts started on it grade on it
    even after a later seed update or studio publish."""
    ScenarioVersion.objects.get_or_create(
        scenario=row, version=row.version,
        defaults={"origin": ScenarioVersion.SEED, "content": row.content,
                  "meta": {f: getattr(row, f) for f in SEED_FIELDS} | {"topic": row.topic.code}},
    )


def skip_reason(row):
    """Why the seed commands must leave this row alone, or "" when they may update it."""
    if row.source == Scenario.STUDIO:
        return "edited in the Practice Studio"
    if row.versions.filter(origin=ScenarioVersion.STUDIO).exists():
        return "has published studio versions"
    if row.content_hash and row.content_hash != content_hash(row.content):
        return "content was changed outside the seed commands"
    return ""


def seed_scenario(data, course, *, force=frozenset(), dry=False):
    """Apply one seed scenario. `data` holds slug, content and SEED_FIELDS.

    Returns (action, detail): action is "create", "update", "unchanged" or "skip"; detail is
    the changed field names (update) or the reason (skip).
    """
    slug = data["slug"]
    new_hash = content_hash(data["content"])
    with transaction.atomic():
        row = Scenario.objects.select_for_update().filter(slug=slug).first()
        if row is None:
            if not dry:
                row = Scenario.objects.create(slug=slug, topic=course, content=data["content"], content_hash=new_hash,
                                              **{f: data.get(f) for f in SEED_FIELDS})
                snapshot_seed(row)
            return "create", ""

        forced = slug in force
        reason = skip_reason(row)
        if reason and not forced:
            logger.warning("seed skipped %s: %s", slug, reason)
            return "skip", reason

        changed = [f for f in SEED_FIELDS if getattr(row, f) != data.get(f)]
        if row.topic_id != course.pk:
            changed.append("topic")
        content_changed = row.content != data["content"]
        if content_changed:
            changed.append("content")
        if forced and (row.source != Scenario.SEED or row.draft_content is not None):
            changed.append("source")
        if not changed:
            if not row.content_hash and not dry:  # rows from before hashes were kept
                Scenario.objects.filter(pk=row.pk).update(content_hash=new_hash)
            return "unchanged", ""
        if dry:
            return "update", ", ".join(changed)

        if content_changed:
            row.content = data["content"]
            row.version += 1
        row.content_hash = new_hash
        row.topic = course
        for f in SEED_FIELDS:
            setattr(row, f, data.get(f))
        if forced:
            row.source = Scenario.SEED
            row.draft_content = None
            row.draft_meta = None
        row.save()
        if content_changed:
            snapshot_seed(row)
        if forced:
            StudioAuditLog.objects.create(
                scenario=row, slug=row.slug, action="seed_force", version=row.version,
                summary=f"Forced seed overwrite ({reason or 'no conflict'}): {', '.join(changed)}"[:255],
            )
        return "update", ", ".join(changed)
