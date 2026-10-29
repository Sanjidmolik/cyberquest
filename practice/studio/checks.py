"""Wizard step 4: the publish checklist.

Every rule is checked separately and shown passed or failed in plain English, with a "Fix"
link to the exact step and field (`<steps URL>#step-3:title`; the editor scrolls there and
focuses the field). The last rule is graders.validate_content() itself, the same check the
player's content must pass, so nothing the friendlier rules miss can be published.
"""

from django.urls import reverse

from ..graders import FLOWS, UNGRADED, validate_content
from .editor import SCHEMA, working_meta
from .serializers import STEP_NAMES, SessionSerializer
from .services import working_content
from .starter_templates import all_templates

EXAMPLE_MIN_LENGTH = 25


def _rule(rules, ok, text, fix=""):
    rules.append({"ok": bool(ok), "text": text, "fix": "" if ok else fix})


def _missing(schema, obj, path=""):
    """(message, field key) for every required text left empty and every list too short/long."""
    problems = []
    for field in schema:
        key, kind = field["key"], field["kind"]
        value = obj.get(key) if isinstance(obj, dict) else None
        if kind in ("text", "textarea") and field.get("required") and not str(value or "").strip():
            problems.append((f"{path}{field['label']} is empty.", key))
        elif kind == "group" and isinstance(value, dict):
            problems += [(m, key) for m, _ in _missing(field["fields"], value, f"{path}{field['label']} → ")]
        elif kind == "rows":
            rows = value if isinstance(value, list) else []
            low, high = field.get("min", 0), field.get("max", 60)
            if len(rows) < low or len(rows) > high:
                want = f"exactly {low}" if low == high else (f"at least {low}" if len(rows) < low else f"at most {high}")
                problems.append((f"{field['label']}: needs {want} (has {len(rows)}).", key))
            for number, row in enumerate(rows, start=1):
                problems += [(m, key) for m, _ in _missing(field["row"], row, f"{field['label']} {number}: ")]
    return problems


def _specific(step_type, data):
    """Answers the forms can't express as 'required': each is (message, field key)."""
    problems = []
    if step_type == "hotspot" and not any(item.get("clue") for item in data.get("items", [])):
        problems.append(("Tick at least one item as a clue.", "items"))
    if step_type == "mcq" and not any(row.get("correct") for row in data.get("options", [])):
        problems.append(("Tick the right answer.", "options"))
    if step_type == "triage" and not isinstance(data.get("severity"), int):
        problems.append(("Choose the right severity.", "severity"))
    if step_type == "configure":
        for number, row in enumerate(data.get("settings", []), start=1):
            options = row.get("options") or []
            if not all(str(option).strip() for option in options):
                problems.append((f"Setting {number}: fill in all three options.", "settings"))
            if not isinstance(row.get("secure"), int):
                problems.append((f"Setting {number}: choose the secure option.", "settings"))
    if step_type == "branch":
        for number, scene in enumerate(data.get("scenes", []), start=1):
            if not any(choice.get("quality") == "good" for choice in scene.get("choices", [])):
                problems.append((f"Scene {number}: mark one choice as Good.", "scenes"))
    return problems


def _strings(value, found=None):
    """Every text of EXAMPLE_MIN_LENGTH or more in `value` (short words like "SENDER" are fine to keep)."""
    found = set() if found is None else found
    if isinstance(value, str) and len(value.strip()) >= EXAMPLE_MIN_LENGTH:
        found.add(value.strip())
    elif isinstance(value, dict):
        for item in value.values():
            _strings(item, found)
    elif isinstance(value, list):
        for item in value:
            _strings(item, found)
    return found


def _template_strings(scenario):
    """Template example texts, minus any this session has ever published (a seed session can
    share text with the template that was based on it, and a restored version keeps its text)."""
    found = set()
    for template in all_templates().values():
        _strings([template["content"].get("steps"), template["content"].get("debrief")], found)
    published = set()
    for content in scenario.versions.values_list("content", flat=True):
        _strings(content, published)
    return found - published


def _contains_any(value, strings):
    if isinstance(value, str):
        return value.strip() in strings
    if isinstance(value, dict):
        return any(_contains_any(v, strings) for v in value.values())
    if isinstance(value, list):
        return any(_contains_any(v, strings) for v in value)
    return False


def run(scenario):
    """[{'ok', 'text', 'fix'}] for every publish rule, in reading order."""
    slug = scenario.slug
    basics_url = reverse("studio:basics", args=[slug])
    steps_url = reverse("studio:steps", args=[slug])
    content = working_content(scenario)
    meta = working_meta(scenario)
    data = SessionSerializer.from_json(content)
    rules = []

    _rule(rules, str(meta["title"] or "").strip(), "The session has a title.", f"{basics_url}#b-title")
    from courses.models import Course
    _rule(rules, Course.objects.filter(pk=meta["topic"]).exists(), "A topic is chosen.", f"{basics_url}#b-topic")

    steps = content.get("steps") or []
    _rule(rules, steps and steps[0].get("type") == "story", "The briefing is the first step.", f"{steps_url}#step-1")
    flow = FLOWS[scenario.kind]
    position, out_of_place = 0, None
    for number, step in enumerate(steps[1:], start=2):
        options = [i for i in range(position + 1, len(flow)) if flow[i] == step.get("type") or step.get("type") == "mcq"]
        if not options:
            out_of_place = out_of_place or number
            continue
        position = options[0]
    order = " → ".join(STEP_NAMES.get(t, t) for t in flow)
    _rule(rules, out_of_place is None, f"The steps follow the {scenario.get_kind_display().lower()} order ({order}).",
          f"{steps_url}#step-{out_of_place or 1}")
    _rule(rules, any(s.get("type") not in UNGRADED for s in steps), "Students answer at least one step.", steps_url)

    for number, row in enumerate(data["steps"], start=1):
        name = STEP_NAMES.get(row["type"], row["type"])
        problems = _missing(SCHEMA.get(row["type"], []), row["data"]) + _specific(row["type"], row["data"])
        if not problems:
            _rule(rules, True, f"Step {number} · {name} is complete.")
        for message, key in problems:
            _rule(rules, False, f"Step {number} · {name}: {message}", f"{steps_url}#step-{number}:{key}")

    debrief = data.get("debrief") or {}
    _rule(rules, str(debrief.get("sub") or "").strip(), "The results screen has a one-line summary.",
          f"{steps_url}#results:sub")

    examples = _template_strings(scenario)
    leftover = next((n for n, s in enumerate(steps, start=1) if _contains_any(s, examples)), None)
    if leftover is None and _contains_any(content.get("debrief"), examples):
        leftover = "results"
    _rule(rules, leftover is None, "No example text from a template is left unchanged.",
          f"{steps_url}#{'results' if leftover == 'results' else f'step-{leftover}'}")

    try:
        validate_content(scenario.kind, content)
        error = ""
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        error = str(exc)
    _rule(rules, not error, "The player's own content check passes." if not error
          else f"The player's own content check fails: {error}.", steps_url)
    return rules


def passed(rules):
    return all(rule["ok"] for rule in rules)
