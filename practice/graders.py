"""Server-side grading for interactive practice sessions.

Each step type has a validator (used by `load_scenarios`) and a grader (used by the
answer API). Answer data lives under the keys in ANSWER_KEYS; `public_content` strips
them so the browser never receives an answer before the learner commits one.
"""

import copy

# Keys that reveal answers. Stripped from everything sent to the browser.
ANSWER_KEYS = {"correct", "effects", "secure", "points", "feedback", "endings", "explanations"}

STEP_TYPES = ("story", "concept_cards", "hotspot", "configure", "mcq", "triage", "order", "match", "branch")
UNGRADED = {"story", "concept_cards"}
# The full flow per kind (HANDOFF.md). Converted scenarios may leave out a step their content
# cannot fill, or use an mcq step in its place, but the order stays the same.
FLOWS = {
    "simulation": ("story", "concept_cards", "hotspot", "configure", "match"),
    "incident": ("story", "triage", "hotspot", "mcq", "order"),
    "choice": ("story", "branch"),
}
START_METERS = {"sec": 50, "trust": 50}


class InvalidAnswer(ValueError):
    """The submitted answer does not fit the step (wrong type, out of range)."""


def public_content(content):
    """A deep copy of the scenario content with every answer key removed."""
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in ANSWER_KEYS}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    return strip(copy.deepcopy(content))


# ---------- answer parsing ----------

def _index(value, size):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < size:
        raise InvalidAnswer("Choose one of the listed options.")
    return value


def _index_list(value, size):
    if not isinstance(value, list):
        raise InvalidAnswer("Expected a list.")
    return [_index(v, size) for v in value]


def _feedback(step, ok):
    fb = (step.get("feedback") or {}).get("good" if ok else "bad") or {}
    return {"title": fb.get("title", "Correct!" if ok else "Not quite"), "text": fb.get("text", "")}


def _result(step, ok, reveal):
    return {"correct": ok, "reveal": reveal, **_feedback(step, ok)}


# ---------- graders: (step, answer) -> {"correct", "title", "text", "reveal"} ----------

def grade_hotspot(step, answer):
    picked = set(_index_list(answer, len(step["items"])))
    correct = set(step["correct"])
    return _result(step, picked == correct, {"correct": sorted(correct)})


def grade_configure(step, answer):
    if not isinstance(answer, dict):
        raise InvalidAnswer("Expected one option per setting.")
    chosen = {}
    for setting in step["settings"]:
        chosen[setting["key"]] = _index(answer.get(setting["key"]), len(setting["options"]))
    secure = {s["key"]: chosen[s["key"]] == s["secure"] for s in step["settings"]}
    points = {s["key"]: s["points"][chosen[s["key"]]] for s in step["settings"]}
    # Threat level: 2 blocked (every setting secure), 1 partial (some protection), 0 exposed.
    threats = []
    for threat in step.get("threats", []):
        keys = threat["settings"]
        if all(secure[k] for k in keys):
            threats.append(2)
        elif any(points[k] > 0 for k in keys):
            threats.append(1)
        else:
            threats.append(0)
    return _result(step, all(secure.values()), {"score": sum(points.values()), "threats": threats, "secure": secure})


def grade_mcq(step, answer):
    """`correct` is one index, or a list when several options are equally right.
    Optional `explanations` (one per option) explain the option the learner picked."""
    picked = _index(answer, len(step["options"]))
    correct = step["correct"] if isinstance(step["correct"], list) else [step["correct"]]
    ok = picked in correct
    result = _result(step, ok, {"correct": correct})
    explanations = step.get("explanations")
    if explanations:
        mine = explanations[picked]
        result["title"] = mine.get("title") or result["title"]
        result["text"] = mine.get("text", "")
        if not ok:
            best = " or ".join(
                f"“{step['options'][i]}” ({explanations[i].get('title', '')})" if explanations[i].get("title")
                else f"“{step['options'][i]}”"
                for i in correct
            )
            result["text"] = f"{result['text']} Best response: {best}.".strip()
    return result


def grade_triage(step, answer):
    picked = _index(answer, len(step["levels"]))
    return _result(step, picked == step["correct"], {"correct": step["correct"]})


def grade_order(step, answer):
    ids = [item["id"] for item in step["items"]]
    if not isinstance(answer, list) or sorted(map(str, answer)) != sorted(map(str, ids)):
        raise InvalidAnswer("Place every step exactly once.")
    order = [str(a) for a in answer]
    correct = [str(c) for c in step["correct"]]
    return _result(step, order == correct, {"correct": step["correct"]})


def grade_match(step, answer):
    left = {str(item["id"]) for item in step["left"]}
    right = {str(item["id"]) for item in step["right"]}
    if not isinstance(answer, list):
        raise InvalidAnswer("Expected a list of pairs.")
    pairs = []
    for pair in answer:
        if not (isinstance(pair, list) and len(pair) == 2):
            raise InvalidAnswer("Each pair needs a problem and a fix.")
        pairs.append((str(pair[0]), str(pair[1])))
    if {p[0] for p in pairs} != left or {p[1] for p in pairs} != right or len(pairs) != len(left):
        raise InvalidAnswer("Match every item exactly once.")
    correct = {(str(l), str(r)) for l, r in step["correct"]}
    marked = [[l, r, (l, r) in correct] for l, r in pairs]
    return _result(step, all(m[2] for m in marked), {"pairs": marked, "correct": step["correct"]})


GRADERS = {
    "hotspot": grade_hotspot,
    "configure": grade_configure,
    "mcq": grade_mcq,
    "triage": grade_triage,
    "order": grade_order,
    "match": grade_match,
}


# ---------- branch: one answer per scene, state kept on the attempt ----------

def branch_ending(step, picks):
    """Ending rule: every call good is the best ending; two or more bad calls is the bad one."""
    endings = step["endings"]
    goods = picks.count("good")
    if goods == len(step["scenes"]):
        key = "best"
    elif picks.count("bad") >= 2:
        key = "bad"
    else:
        key = "mid"
    return key, endings[key]


def grade_branch(step, answer, state):
    """Apply one scene choice. Mutates and returns `state` alongside the response."""
    if not isinstance(answer, dict):
        raise InvalidAnswer("Expected a scene and a choice.")
    scene_no = state.get("scene", 0)
    if answer.get("scene") != scene_no or scene_no >= len(step["scenes"]):
        raise InvalidAnswer("That scene is not the current one.")
    scene = step["scenes"][scene_no]
    choice = scene["choices"][_index(answer.get("choice"), len(scene["choices"]))]
    effects = choice["effects"]
    meters = state.get("meters") or dict(START_METERS)
    meters = {
        "sec": max(0, min(100, meters["sec"] + effects["sec"])),
        "trust": max(0, min(100, meters["trust"] + effects["trust"])),
    }
    picks = list(state.get("picks", [])) + [effects["kind"]]
    next_scene = scene_no + 1
    response = {
        "correct": effects["kind"] == "good",
        "effects": {"sec": effects["sec"], "trust": effects["trust"], "kind": effects["kind"]},
        "outcome_text": effects["out"],
        "meters": meters,
        "next_scene": next_scene if next_scene < len(step["scenes"]) else None,
    }
    state.update({"scene": next_scene, "picks": picks, "meters": meters})
    if response["next_scene"] is None:
        key, ending = branch_ending(step, picks)
        state["ending"] = key
        response["ending"] = {"key": key, **ending}
    return response, state


# ---------- content validation (load_scenarios) ----------

def _need(step, *keys):
    missing = [k for k in keys if k not in step]
    if missing:
        raise ValueError(f"{step.get('type')} step is missing {', '.join(missing)}")


def validate_step(step):
    kind = step.get("type")
    if kind not in STEP_TYPES:
        raise ValueError(f"unknown step type {kind!r}")
    if kind == "concept_cards":
        _need(step, "title", "cards")
    elif kind == "hotspot":
        _need(step, "title", "items", "correct", "feedback")
        _index_list(step["correct"], len(step["items"]))
    elif kind == "configure":
        _need(step, "title", "settings", "feedback")
        for s in step["settings"]:
            _need(s, "key", "label", "options", "secure", "points")
            _index(s["secure"], len(s["options"]))
            if len(s["points"]) != len(s["options"]):
                raise ValueError(f"setting {s['key']} needs one point value per option")
        keys = {s["key"] for s in step["settings"]}
        for t in step.get("threats", []):
            if not set(t["settings"]) <= keys:
                raise ValueError(f"threat {t['label']} names an unknown setting")
    elif kind == "mcq":
        _need(step, "options", "correct", "feedback")
        for i in (step["correct"] if isinstance(step["correct"], list) else [step["correct"]]):
            _index(i, len(step["options"]))
        if step.get("explanations") and len(step["explanations"]) != len(step["options"]):
            raise ValueError("mcq step needs one explanation per option")
    elif kind == "triage":
        _need(step, "title", "alerts", "levels", "correct", "feedback")
        _index(step["correct"], len(step["levels"]))
    elif kind == "order":
        _need(step, "title", "items", "correct", "feedback")
        if sorted(map(str, step["correct"])) != sorted(str(i["id"]) for i in step["items"]):
            raise ValueError("order step: correct must list every item id once")
    elif kind == "match":
        _need(step, "left", "right", "correct", "feedback")
        left = sorted(str(i["id"]) for i in step["left"])
        right = sorted(str(i["id"]) for i in step["right"])
        if sorted(str(p[0]) for p in step["correct"]) != left or sorted(str(p[1]) for p in step["correct"]) != right:
            raise ValueError("match step: correct must pair every left and right item once")
    elif kind == "branch":
        _need(step, "scenes", "endings")
        if set(step["endings"]) != {"best", "mid", "bad"}:
            raise ValueError("branch step needs best, mid and bad endings")
        for scene in step["scenes"]:
            for choice in scene["choices"]:
                _need(choice, "text", "effects")
                _need(choice["effects"], "sec", "trust", "kind", "out")
                if choice["effects"]["kind"] not in ("good", "meh", "bad"):
                    raise ValueError("branch choice kind must be good, meh or bad")


def validate_content(kind, content):
    steps = content.get("steps") or []
    for step in steps:
        validate_step(step)
    if not steps or steps[0]["type"] != "story":
        raise ValueError("the first step must be the story (briefing)")
    # Each later step must be the next step of the kind's flow, or an mcq standing in for one.
    position = 0
    full = FLOWS[kind]
    for step in steps[1:]:
        options = [i for i in range(position + 1, len(full)) if full[i] == step["type"] or step["type"] == "mcq"]
        if not options:
            raise ValueError(f"{kind} flow is {' → '.join(full)}; {step['type']} is out of place")
        position = options[0]
    if not any(step["type"] not in UNGRADED for step in steps):
        raise ValueError("a scenario needs at least one graded step")
    if not content.get("debrief"):
        raise ValueError("content needs a debrief block")
