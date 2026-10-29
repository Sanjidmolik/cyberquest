"""Creating Practice Studio drafts: duplicate, start from a template, import a file.

Every new session is a DRAFT with source "studio", so students never see it and the seed
commands never touch it. `content` holds the session as created; edits go to `draft_content`
until they are published.
"""

import copy
import json

from django.db import transaction
from django.utils.text import slugify

from ..conversion import XP_REWARD as STUDIO_XP   # every Studio session is worth the practice rule: 50 XP
from ..graders import FLOWS, validate_content
from ..models import Scenario, StudioAuditLog
from .starter_templates import load_template

DIFFICULTIES = ("beginner", "intermediate", "advanced")
EXPORT_FORMAT = "cyberquest-practice-session"
EXPORT_VERSION = 1
MAX_IMPORT_BYTES = 1024 * 1024
# Provenance of a seed scenario (practice.conversion). A copy is a new session, so it must not
# claim the original's key: history, Cyber DNA and the catalog would treat it as the original.
PROVENANCE_KEYS = ("source",)


class SessionFileError(ValueError):
    """The uploaded file can't become a session. `messages` lists every reason in plain English."""

    def __init__(self, messages):
        super().__init__("; ".join(messages))
        self.messages = list(messages)


def unique_slug(title):
    base = (slugify(title)[:40].strip("-") or "practice-session")
    slug, n = base, 2
    while Scenario.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}"[:50], n + 1
    return slug


def session_content(content):
    """A copy of content without seed provenance, ready to become a new session."""
    out = copy.deepcopy(content)
    for key in PROVENANCE_KEYS:
        out.pop(key, None)
    return out


def _create(*, user, action, summary, topic, kind, title, difficulty, est_minutes, content):
    with transaction.atomic():
        scenario = Scenario.objects.create(
            slug=unique_slug(title), topic=topic, kind=kind, title=title[:160], difficulty=difficulty,
            est_minutes=est_minutes, time_limit_sec=None, xp_reward=STUDIO_XP, content=content,
            status=Scenario.DRAFT, source=Scenario.STUDIO, created_by=user, updated_by=user,
        )
        StudioAuditLog.objects.create(user=user, scenario=scenario, slug=scenario.slug, action=action,
                                      version=scenario.version, summary=summary[:255])
    return scenario


def working_content(scenario):
    """What the studio edits: the unpublished draft if there is one, else the published content."""
    return scenario.draft_content if scenario.draft_content is not None else scenario.content


def duplicate(source, user):
    """A new draft with the same topic, kind, settings and content (minus seed provenance)."""
    return _create(
        user=user, action="duplicate", summary=f"Copy of {source.slug} v{source.version}",
        topic=source.topic, kind=source.kind, title=f"{source.title} (copy)", difficulty=source.difficulty,
        est_minutes=source.est_minutes, content=session_content(working_content(source)),
    )


def from_template(kind, topic, user):
    template = load_template(kind)
    return _create(
        user=user, action="create", summary=f"From the {kind} template v{template['template_version']}",
        topic=topic, kind=kind, title=template["title"], difficulty=template["difficulty"],
        est_minutes=template["est_minutes"], content=copy.deepcopy(template["content"]),
    )


def export_payload(scenario, content=None):
    """The file another CyberQuest instance can import (Studio -> Import file)."""
    return {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_VERSION,
        "slug": scenario.slug,
        "topic": scenario.topic.code,
        "kind": scenario.kind,
        "title": scenario.title,
        "difficulty": scenario.difficulty,
        "est_minutes": scenario.est_minutes,
        "xp_reward": scenario.xp_reward,
        "content": session_content(content if content is not None else scenario.content),
    }


def _whole_number(data, key, low, high, errors, label):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        errors.append(f"{label} must be a whole number from {low} to {high}.")
        return None
    return value


def parse_import(raw, topic=None):
    """Check an uploaded file and return the fields of a new session. Raises SessionFileError with
    every problem found. `topic` (a Course) overrides the file's topic code."""
    from courses.models import Course

    if len(raw) > MAX_IMPORT_BYTES:
        raise SessionFileError([f"The file is larger than {MAX_IMPORT_BYTES // 1024} KB."])
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError:
        raise SessionFileError(["The file is not UTF-8 text."])
    except ValueError as exc:
        raise SessionFileError([f"The file is not valid JSON ({exc.msg}, line {exc.lineno})."])
    if not isinstance(data, dict):
        raise SessionFileError(["The file must hold one practice session (a JSON object)."])
    if data.get("format") not in (None, EXPORT_FORMAT):
        raise SessionFileError(["This is not a CyberQuest practice session file."])

    errors = []
    kind = data.get("kind")
    if kind not in FLOWS:
        errors.append("Kind must be simulation, incident or choice.")
    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("The session needs a title.")
    difficulty = data.get("difficulty")
    if difficulty not in DIFFICULTIES:
        errors.append("Difficulty must be beginner, intermediate or advanced.")
    minutes = _whole_number(data, "est_minutes", 1, 120, errors, "Estimated minutes")
    if topic is None:
        topic = Course.objects.filter(code=data.get("topic")).first() if isinstance(data.get("topic"), str) else None
        if topic is None:
            errors.append(f"The topic {data.get('topic')!r} doesn't exist here: choose a topic for it.")
    content = data.get("content")
    if not isinstance(content, dict):
        errors.append("The file has no session content.")
    elif kind in FLOWS:
        try:
            validate_content(kind, content)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            errors.append(f"The session content is not valid: {exc}.")
    if errors:
        raise SessionFileError(errors)
    return {"topic": topic, "kind": kind, "title": title.strip(), "difficulty": difficulty, "est_minutes": minutes,
            "content": session_content(content), "file_slug": data.get("slug")}


def import_session(raw, user, topic=None, filename=""):
    fields = parse_import(raw, topic)
    origin = fields.pop("file_slug")
    summary = f"Imported from {filename or 'a file'}" + (f" (was {origin})" if isinstance(origin, str) else "")
    return _create(user=user, action="import", summary=summary, **fields)
