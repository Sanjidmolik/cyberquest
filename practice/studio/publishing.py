"""Wizard step 4: publish, archive, un-archive, restore, request review.

- Every action locks the row and writes an audit entry. Publish and restore also check the
  draft revision (editor.Conflict), so nobody publishes or overwrites a draft they haven't seen.
- Publish runs the checklist (checks.py) again on the server; the button alone proves nothing.
- Before the live content is replaced, its version is kept as a snapshot, so a student
  mid-session keeps playing (and is graded on) the version they started.
- Archive only changes the status: attempts, history and XP stay as they are.
- Restore copies an old version into the DRAFT. It never publishes.
The views check who may do what (practice.publish_scenario); these functions trust them.
"""

import copy
import difflib
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Q
from django.urls import reverse
from django.utils import timezone

from ..models import Scenario, ScenarioVersion, StudioAuditLog
from ..seeding import SEED_FIELDS, canonical_json
from . import checks
from .editor import XP_REWARD, Conflict, EditorError
from .serializers import STEP_NAMES
from .services import working_content

REVIEW_COOLDOWN = timedelta(minutes=10)


class ChecksFailed(EditorError):
    def __init__(self, rules):
        failed = [rule["text"] for rule in rules if not rule["ok"]]
        super().__init__(f"Not published: {_plural(len(failed), 'check')} still to fix.")
        self.rules = rules


def _locked(scenario_pk, revision=None):
    row = Scenario.objects.select_for_update().select_related("topic", "draft_saved_by").get(pk=scenario_pk)
    if revision is not None and revision != row.draft_revision:
        raise Conflict(row.draft_saved_by.username if row.draft_saved_by else "another editor", row.draft_saved_at)
    return row


def _audit(user, row, action, summary):
    StudioAuditLog.objects.create(user=user, scenario=row, slug=row.slug, action=action, version=row.version,
                                  summary=summary[:255])


def _row_meta(row):
    return {f: getattr(row, f) for f in SEED_FIELDS} | {"topic": row.topic.code}


def was_published(row):
    return row.status != Scenario.DRAFT or row.versions.exists()


def _keep_live_version(row):
    """Snapshot what students can play now, if it isn't one yet (rows from before snapshots)."""
    if was_published(row) and not row.versions.filter(version=row.version).exists():
        ScenarioVersion.objects.create(
            scenario=row, version=row.version, content=row.content, meta=_row_meta(row),
            origin=ScenarioVersion.SEED if row.source == Scenario.SEED else ScenarioVersion.STUDIO)


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def what_changed(old_content, old_meta, new_content, new_meta):
    """Plain-English lines: steps added/removed/edited, title and setting changes."""
    if old_content is None:
        return ["First published version"]
    lines = []
    if old_meta.get("title") != new_meta.get("title"):
        lines.append(f"Title: “{old_meta.get('title')}” → “{new_meta.get('title')}”")
    for key, label in (("difficulty", "Difficulty"), ("est_minutes", "Minutes"), ("topic", "Topic")):
        if old_meta.get(key) != new_meta.get(key):
            lines.append(f"{label}: {old_meta.get(key)} → {new_meta.get(key)}")
    old_steps, new_steps = old_content.get("steps") or [], new_content.get("steps") or []
    matcher = difflib.SequenceMatcher(a=[s.get("type") for s in old_steps], b=[s.get("type") for s in new_steps],
                                      autojunk=False)
    added, removed, edited = [], [], 0
    for op, a1, a2, b1, b2 in matcher.get_opcodes():
        if op == "equal":
            edited += sum(canonical_json(old_steps[a1 + i]) != canonical_json(new_steps[b1 + i]) for i in range(a2 - a1))
        if op in ("delete", "replace"):
            removed += [STEP_NAMES.get(s.get("type"), s.get("type")) for s in old_steps[a1:a2]]
        if op in ("insert", "replace"):
            added += [STEP_NAMES.get(s.get("type"), s.get("type")) for s in new_steps[b1:b2]]
    if added:
        lines.append(f"Added {_plural(len(added), 'step')}: {', '.join(added)}")
    if removed:
        lines.append(f"Removed {_plural(len(removed), 'step')}: {', '.join(removed)}")
    if edited:
        lines.append(f"Edited {_plural(edited, 'step')}")
    if canonical_json(old_content.get("debrief")) != canonical_json(new_content.get("debrief")):
        lines.append("Edited the results screen")
    if canonical_json(old_content.get("meta")) != canonical_json(new_content.get("meta")):
        lines.append("Edited the badge or description")
    return lines or ["No visible changes"]


def has_changes(row):
    return row.draft_content is not None or bool(row.draft_meta)


def publish(scenario_pk, user, *, revision):
    """Make the draft what students play. Raises Conflict, ChecksFailed or EditorError."""
    from courses.models import Course
    with transaction.atomic():
        row = _locked(scenario_pk, revision)
        if row.status == Scenario.PUBLISHED and not has_changes(row):
            raise EditorError("There is nothing new to publish: students already see this version.")
        rules = checks.run(row)
        if not checks.passed(rules):
            raise ChecksFailed(rules)

        first = not was_published(row)
        old_content = None if first else copy.deepcopy(row.content)
        old_meta = None if first else _row_meta(row)
        _keep_live_version(row)
        if not first:
            row.version = max(row.version, row.versions.aggregate(top=Max("version"))["top"] or 0) + 1

        meta = row.draft_meta or {}
        row.content = working_content(row)
        row.title = meta.get("title") or row.title
        row.difficulty = meta.get("difficulty", row.difficulty)
        row.est_minutes = meta.get("est_minutes", row.est_minutes)
        if meta.get("topic"):
            row.topic = Course.objects.get(pk=meta["topic"])
        row.xp_reward = XP_REWARD
        row.draft_content, row.draft_meta = None, None
        row.draft_revision += 1                         # open editors must reload before saving again
        row.status, row.source, row.updated_by = Scenario.PUBLISHED, Scenario.STUDIO, user
        row.save()

        changes = what_changed(old_content, old_meta, row.content, _row_meta(row))
        ScenarioVersion.objects.create(scenario=row, version=row.version, origin=ScenarioVersion.STUDIO,
                                       content=row.content, meta=_row_meta(row) | {"changes": changes},
                                       published_by=user)
        _audit(user, row, "publish", f"Published v{row.version}: {'; '.join(changes)}")
    return row


def archive(scenario_pk, user):
    """Hide the session from the Practice Center. Nothing is deleted."""
    with transaction.atomic():
        row = _locked(scenario_pk)
        if row.status == Scenario.ARCHIVED:
            raise EditorError("This session is already archived.")
        _keep_live_version(row)
        row.status, row.updated_by = Scenario.ARCHIVED, user
        row.save(update_fields=["status", "updated_by", "updated_at"])
        _audit(user, row, "archive", f"Archived v{row.version}; students' history and XP are kept")
    return row


def unarchive(scenario_pk, user):
    """Back to published (the last published version) or, if it never was, back to draft."""
    with transaction.atomic():
        row = _locked(scenario_pk)
        if row.status != Scenario.ARCHIVED:
            raise EditorError("This session isn't archived.")
        row.status = Scenario.PUBLISHED if row.versions.filter(version=row.version).exists() else Scenario.DRAFT
        row.updated_by = user
        row.save(update_fields=["status", "updated_by", "updated_at"])
        _audit(user, row, "unarchive", f"Un-archived as {row.get_status_display().lower()} (v{row.version})")
    return row


def restore(scenario_pk, user, *, version, revision):
    """Copy a published version into the draft. Students keep seeing the live version."""
    from courses.models import Course
    with transaction.atomic():
        row = _locked(scenario_pk, revision)
        snapshot = row.versions.filter(version=version).first()
        if snapshot is None:
            raise EditorError("That version doesn't exist.")
        meta = snapshot.meta or {}
        topic = Course.objects.filter(code=meta.get("topic")).values_list("pk", flat=True).first() or row.topic_id
        row.draft_content = copy.deepcopy(snapshot.content)
        row.draft_meta = {"title": meta.get("title") or row.title, "difficulty": meta.get("difficulty", row.difficulty),
                          "est_minutes": meta.get("est_minutes", row.est_minutes), "topic": topic}
        row.draft_revision += 1
        row.draft_saved_by, row.draft_saved_at = user, timezone.now()
        row.source, row.updated_by = Scenario.STUDIO, user
        row.save()
        _audit(user, row, "restore", f"Restored v{snapshot.version} as a draft (live version v{row.version} unchanged)")
    return row


def publishers():
    """Active staff who may publish: superusers and anyone with practice.publish_scenario."""
    perm = Q(groups__permissions__codename="publish_scenario") | Q(user_permissions__codename="publish_scenario")
    return (get_user_model().objects.filter(is_active=True)
            .filter(Q(is_superuser=True) | (Q(is_staff=True) & perm)).distinct())


def request_review(scenario_pk, user):
    """Tell the publishers this draft is ready. Returns how many were notified (0 if a review
    was already requested in the last few minutes)."""
    from notifications.utils import notify
    with transaction.atomic():
        row = _locked(scenario_pk)
        recent = row.audit.filter(action="review", created_at__gte=timezone.now() - REVIEW_COOLDOWN).exists()
        if recent:
            return 0
        title = (row.draft_meta or {}).get("title") or row.title
        link = reverse("studio:check", args=[row.slug])
        people = list(publishers().exclude(pk=user.pk))
        for person in people:
            notify(person, f"{user.username} asked you to review the practice session “{title}”."[:255], link)
        _audit(user, row, "review", f"Asked {_plural(len(people), 'publisher')} for a review")
    return len(people)
