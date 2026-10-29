"""The Studio preview's answer key: the right answers per step, in plain words, built on the
server from the saved draft. It is shown to Studio staff beside (never inside) the player
iframe; the player and the student API keep receiving content without answers."""

from ..conversion import SEVERITY
from .serializers import SERIALIZERS, STEP_NAMES

QUALITY = {"good": "Good", "meh": "Risky", "bad": "Bad"}


def _lines(step_type, data):
    if step_type == "story":
        return ["Briefing: nothing to answer."]
    if step_type == "concept_cards":
        return ["Learn cards: nothing to answer (flip all three)."]
    if step_type == "hotspot":
        clues = [item.get("label") or "(no label)" for item in data.get("items", []) if item.get("clue")]
        return [f"Pick these {len(clues)}:"] + [f"• {clue}" for clue in clues] if clues else ["No clue ticked yet."]
    if step_type == "configure":
        out = []
        for row in data.get("settings", []):
            options, secure = row.get("options") or [], row.get("secure")
            choice = options[secure] if isinstance(secure, int) and 0 <= secure < len(options) else "(not chosen)"
            out.append(f"• {row.get('label') or '(setting)'}: {choice or '(empty option)'}")
        return out or ["No settings yet."]
    if step_type == "mcq":
        right = [row.get("text") or "(empty answer)" for row in data.get("options", []) if row.get("correct")]
        return [f"• {text}" for text in right] or ["No right answer ticked yet."]
    if step_type == "triage":
        levels = data.get("levels") or [label for _, label, _, _ in SEVERITY]
        severity = data.get("severity")
        return [f"Severity: {levels[severity]}" if isinstance(severity, int) and 0 <= severity < len(levels)
                else "Severity not chosen yet."]
    if step_type == "order":
        return [f"{n}. {row.get('text') or '(empty step)'}" for n, row in enumerate(data.get("steps", []), start=1)] \
            or ["No steps yet."]
    if step_type == "match":
        return [f"• {row.get('left') or '?'} → {row.get('right') or '?'}" for row in data.get("pairs", [])] or ["No pairs yet."]
    if step_type == "branch":
        out = []
        for n, scene in enumerate(data.get("scenes", []), start=1):
            out.append(f"Scene {n}: {scene.get('title') or ''}".strip())
            out += [f"   {QUALITY.get(c.get('quality'), c.get('quality'))}: {c.get('text') or '(empty choice)'}"
                    for c in scene.get("choices", [])]
        return out or ["No scenes yet."]
    return []


def answer_key(content):
    """[{'number', 'name', 'lines'}] for every step of `content`."""
    key = []
    for number, step in enumerate(content.get("steps") or [], start=1):
        serializer = SERIALIZERS.get(step.get("type"))
        data = serializer.from_json(step) if serializer else {}
        key.append({"number": number, "name": STEP_NAMES.get(step.get("type"), step.get("type")),
                    "lines": _lines(step.get("type"), data)})
    return key
