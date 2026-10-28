"""Scenario content <-> Practice Studio form data, one class per step type.

`from_json(step)` gives the plain values a step's form shows: text, rows, ticks and radio
choices, never indexes or JSON. `to_json(data, original)` writes them back by MERGING into a
copy of the original step: a value is written only where the admin changed it, and every key
the form does not show (unknown or future keys, tips the player doesn't use, hand-tuned
points and effects, colours) is kept as it was. So from_json -> to_json with no edits gives
back the original exactly, and one edit changes only what it touches (plus values derived from
it, such as `correct` from the ticked clues).

Repeated rows carry `uid`: the row's index (or id, for order and match) in the original step,
or None for a new row. Rows can be reordered, added and removed; each keeps its own unknown keys.
"""

import copy
import random
import re

from ..conversion import ALERT_COLOURS, STEP_LABEL

# Labels for the briefing's step list, for step types the converter never makes.
DEFAULT_LABELS = {**STEP_LABEL, "configure": "Lock down", "order": "Respond", "branch": "Decide", "story": "Brief"}
# Default meter changes per choice quality (the most common values in the existing content).
DEFAULT_EFFECTS = {"good": (25, 10), "meh": (-10, 0), "bad": (-25, -10)}
QUALITY_CHOICES = [("good", "Good"), ("meh", "Risky"), ("bad", "Bad")]
LAYOUT_CHOICES = [("flow", "Workflow diagram"), ("fields", "Detail list")]
MOODS = ["neutral", "smile", "talk", "think", "happy", "surprised", "correct", "wrong"]
# Hana's lines each step type actually says (static/practice/js/steps/*.js).
TIP_KEYS = {
    "concept_cards": ("start", "progress", "done"),
    "hotspot": ("start", "progress", "ready", "good", "bad"),
    "configure": ("start", "progress", "good", "bad"),
    "mcq": ("start", "ready", "good", "bad"),
    "triage": ("start", "all_in", "ready", "good", "bad"),
    "order": ("start", "progress", "ready", "good", "bad"),
    "match": ("start", "progress", "ready", "good", "bad"),
}
FEEDBACK_KEYS = ("title", "text")


# ---------- merge helpers ----------

def _text(d, key):
    value = (d or {}).get(key)
    return "" if value is None else value


def _put(target, key, new, old):
    """Write `new` only where the admin changed it. An emptied optional value removes the key."""
    if new == old:
        return
    if new in ("", None):
        target.pop(key, None)
    else:
        target[key] = new


def _texts_from(d, keys):
    return {k: _text(d, k) for k in keys}


def _texts_into(target, key, new, old):
    """Merge a {key: text} group (tips, feedback, labels) into target[key], keeping other keys."""
    if new == old:
        return
    group = copy.deepcopy(target.get(key) or {})
    for k, value in new.items():
        _put(group, k, value, old.get(k, ""))
    if group:
        target[key] = group
    else:
        target.pop(key, None)


def _feedback_from(step):
    fb = step.get("feedback") or {}
    return {side: _texts_from(fb.get(side), FEEDBACK_KEYS) for side in ("good", "bad")}


def _feedback_into(step, new, old):
    if new == old:
        return
    fb = copy.deepcopy(step.get("feedback") or {})
    for side in ("good", "bad"):
        _texts_into(fb, side, new[side], old[side])
    step["feedback"] = fb


def _base_rows(original_rows, uid):
    if isinstance(uid, int) and not isinstance(uid, bool) and 0 <= uid < len(original_rows):
        return copy.deepcopy(original_rows[uid])
    return None


def _merge_rows(original_rows, before_rows, rows, write):
    """Rebuild a list of rows: each from its original (by uid) with only changed fields written."""
    before = {r["uid"]: r for r in before_rows if r.get("uid") is not None}
    out = []
    for position, row in enumerate(rows):
        uid = row.get("uid")
        base = _base_rows(original_rows, uid)
        out.append(write(base if base is not None else {}, row, before.get(uid) if base is not None else None, position))
    return out


def _fields_into(target, row, old, fields):
    for f in fields:
        _put(target, f, row.get(f, ""), (old or {}).get(f, None if old is None else ""))


def _initials(text):
    words = [w for w in str(text).replace("(", " ").split() if w[:1].isalnum()]
    return ("".join(w[0] for w in words[:2]) or "?").upper()


def _new_id(prefix, taken):
    n = 1
    while f"{prefix}{n}" in taken:
        n += 1
    taken.add(f"{prefix}{n}")
    return f"{prefix}{n}"


def _slug_key(label, taken):
    base = re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_")[:24] or "setting"
    key, n = base, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    taken.add(key)
    return key


# ---------- one serializer per step type ----------

class StepSerializer:
    type = ""
    skeleton = {}

    @classmethod
    def blank(cls):
        return {"type": cls.type, **copy.deepcopy(cls.skeleton)}

    @classmethod
    def from_json(cls, step):
        raise NotImplementedError

    @classmethod
    def to_json(cls, data, original=None):
        """`data` as from_json returns it (possibly edited), merged into `original`."""
        step = copy.deepcopy(original) if original else cls.blank()
        before = cls.from_json(original) if original else cls.from_json(cls.blank())
        cls.write(step, data, before, original or cls.blank())
        return step

    @classmethod
    def write(cls, step, data, before, original):
        raise NotImplementedError

    # Shared: Hana's lines and the good / bad feedback.
    @classmethod
    def _common_from(cls, step):
        data = {}
        if cls.type in TIP_KEYS:
            data["tips"] = _texts_from(step.get("tips"), TIP_KEYS[cls.type])
        if cls.type not in ("story", "concept_cards", "branch"):
            data["feedback"] = _feedback_from(step)
        return data

    @classmethod
    def _common_into(cls, step, data, before):
        if "tips" in before:
            _texts_into(step, "tips", data["tips"], before["tips"])
        if "feedback" in before:
            _feedback_into(step, data["feedback"], before["feedback"])


class StorySerializer(StepSerializer):
    type = "story"
    skeleton = {"desc": "", "intro": "", "labels": [], "end_expression": "smile"}

    @classmethod
    def from_json(cls, step):
        return {"intro": _text(step, "intro"), "desc": _text(step, "desc"), "mood": _text(step, "end_expression")}

    @classmethod
    def write(cls, step, data, before, original):
        _put(step, "intro", data["intro"], before["intro"])
        _put(step, "desc", data["desc"], before["desc"])
        _put(step, "end_expression", data["mood"], before["mood"])


class ConceptCardsSerializer(StepSerializer):
    type = "concept_cards"
    skeleton = {"title": "", "cards": []}
    ROW = ("icon", "title", "back")

    @classmethod
    def from_json(cls, step):
        return {
            "title": _text(step, "title"),
            "cards": [{"uid": i, **_texts_from(c, cls.ROW)} for i, c in enumerate(step.get("cards") or [])],
            **cls._common_from(step),
        }

    @classmethod
    def write(cls, step, data, before, original):
        _put(step, "title", data["title"], before["title"])

        def card(base, row, old, _pos):
            _fields_into(base, row, old, cls.ROW)
            return base
        step["cards"] = _merge_rows(original.get("cards") or [], before["cards"], data["cards"], card)
        cls._common_into(step, data, before)


class HotspotSerializer(StepSerializer):
    type = "hotspot"
    skeleton = {"layout": "fields", "title": "", "select": 0, "items": [], "correct": [], "feedback": {}}
    ITEM = ("label", "value", "icon")
    LABEL_KEYS = ("pick", "right", "wrong", "missed")

    @classmethod
    def from_json(cls, step):
        correct = set(step.get("correct") or [])
        return {
            "title": _text(step, "title"),
            "banner": _text(step, "banner"),
            "layout": _text(step, "layout"),
            "items": [{"uid": i, **_texts_from(it, cls.ITEM), "clue": i in correct}
                      for i, it in enumerate(step.get("items") or [])],
            "context": [
                {"uid": i, "title": _text(panel, "title"),
                 "rows": [{"uid": j, "label": _text(r, "label"), "value": _text(r, "value"), "flag": bool(r.get("flag"))}
                          for j, r in enumerate(panel.get("rows") or [])]}
                for i, panel in enumerate(step.get("context") or [])
            ],
            "labels": _texts_from(step.get("labels"), cls.LABEL_KEYS),
            **cls._common_from(step),
        }

    @classmethod
    def write(cls, step, data, before, original):
        for key in ("title", "banner", "layout"):
            _put(step, key, data[key], before[key])

        def item(base, row, old, _pos):
            _fields_into(base, row, old, cls.ITEM)
            return base
        step["items"] = _merge_rows(original.get("items") or [], before["items"], data["items"], item)
        # The answer is whichever rows are ticked as clues; "need" (select) is how many.
        # Kept as stored (in its stored order) while the same rows stay ticked in the same places.
        ticked = [i for i, row in enumerate(data["items"]) if row.get("clue")]
        old_correct = list(original.get("correct") or [])
        moved = [r.get("uid") for r in data["items"]] != [r["uid"] for r in before["items"]]
        if moved or ticked != sorted(old_correct):
            step["correct"] = ticked
            if original.get("select") in (None, len(old_correct)):
                step["select"] = len(ticked)

        if data["context"] != before["context"]:
            original_panels = original.get("context") or []
            before_panels = {p["uid"]: p for p in before["context"]}

            def panel(base, row, old, _pos):
                _put(base, "title", row.get("title", ""), (old or {}).get("title"))

                def cell(cbase, crow, cold, _p):
                    _fields_into(cbase, crow, cold, ("label", "value"))
                    if crow.get("flag") != (cold or {}).get("flag", None if cold is None else False):
                        cbase["flag"] = bool(crow.get("flag"))
                    return cbase
                base["rows"] = _merge_rows(base.get("rows") or [], (old or {}).get("rows") or [], row.get("rows") or [], cell)
                return base
            panels = _merge_rows(original_panels, list(before_panels.values()), data["context"], panel)
            if panels:
                step["context"] = panels
            else:
                step.pop("context", None)
        _texts_into(step, "labels", data["labels"], before["labels"])
        cls._common_into(step, data, before)


class ConfigureSerializer(StepSerializer):
    type = "configure"
    skeleton = {"title": "", "console_title": "", "check_label": "", "settings": [], "threats": [], "feedback": {}}
    DEFAULT_POINTS = {3: [0, 10, 30]}

    @classmethod
    def _single_threats(cls, step):
        return {t["settings"][0]: t.get("label", "") for t in step.get("threats") or [] if len(t.get("settings") or []) == 1}

    @classmethod
    def from_json(cls, step):
        single = cls._single_threats(step)
        return {
            "title": _text(step, "title"),
            "console_title": _text(step, "console_title"),
            "check_label": _text(step, "check_label"),
            "settings": [
                {"uid": i, "label": _text(s, "label"), "hint": _text(s, "hint"), "threat": single.get(s.get("key"), ""),
                 "options": list(s.get("options") or []), "secure": s.get("secure")}
                for i, s in enumerate(step.get("settings") or [])
            ],
            **cls._common_from(step),
        }

    @classmethod
    def _points(cls, options, secure):
        size = len(options)
        if size in cls.DEFAULT_POINTS and secure == size - 1:
            return list(cls.DEFAULT_POINTS[size])
        return [30 if i == secure else (10 if i == secure - 1 else 0) for i in range(size)]

    @classmethod
    def write(cls, step, data, before, original):
        for key in ("title", "console_title", "check_label"):
            _put(step, key, data[key], before[key])
        if data["settings"] == before["settings"]:
            cls._common_into(step, data, before)
            return
        taken = {s.get("key") for s in original.get("settings") or []}

        def setting(base, row, old, _pos):
            if "key" not in base:
                base["key"] = _slug_key(row.get("label"), taken)
            _fields_into(base, row, old, ("label", "hint"))
            options, secure = list(row.get("options") or []), row.get("secure")
            if old is None or options != old["options"] or secure != old["secure"]:
                base["options"], base["secure"] = options, secure
                if old is None or len(options) != len(old["options"]) or secure != old["secure"] or "points" not in base:
                    base["points"] = cls._points(options, secure)
            return base
        step["settings"] = _merge_rows(original.get("settings") or [], before["settings"], data["settings"], setting)

        # Threats: one per setting row (its threat name); threats that span several settings are
        # not in the form and are kept while all their settings still exist.
        keys = [s["key"] for s in step["settings"]]
        wanted = {s["key"]: row.get("threat", "") for s, row in zip(step["settings"], data["settings"])}
        threats, seen = [], set()
        for t in original.get("threats") or []:
            names = t.get("settings") or []
            if len(names) == 1:
                key = names[0]
                if wanted.get(key):
                    threats.append({**copy.deepcopy(t), "label": wanted[key]})
                    seen.add(key)
            elif set(names) <= set(keys):
                threats.append(copy.deepcopy(t))
        threats += [{"label": wanted[k], "settings": [k]} for k in keys if wanted.get(k) and k not in seen]
        step["threats"] = threats
        cls._common_into(step, data, before)


class McqSerializer(StepSerializer):
    type = "mcq"
    skeleton = {"eyebrow": "", "options": [], "correct": 0, "feedback": {}}

    @classmethod
    def from_json(cls, step):
        correct = step.get("correct")
        right = set(correct if isinstance(correct, list) else [correct])
        explanations = step.get("explanations") or []
        rows = []
        for i, text in enumerate(step.get("options") or []):
            expl = explanations[i] if i < len(explanations) else {}
            rows.append({"uid": i, "text": text, "correct": i in right,
                         "explanation_title": _text(expl, "title"), "explanation_text": _text(expl, "text")})
        common = cls._common_from(step)
        return {"eyebrow": _text(step, "eyebrow"), "question": common["tips"]["start"], "options": rows, **common}

    @classmethod
    def write(cls, step, data, before, original):
        _put(step, "eyebrow", data["eyebrow"], before["eyebrow"])
        # The question is what Hana asks: tips.start.
        data = {**data, "tips": {**data["tips"], "start": data["question"]}}
        before = {**before, "tips": {**before["tips"], "start": before["question"]}}
        if data["options"] != before["options"]:
            rows = data["options"]
            step["options"] = [r.get("text", "") for r in rows]
            right = [i for i, r in enumerate(rows) if r.get("correct")]
            old = original.get("correct")
            if sorted(right) != sorted(old if isinstance(old, list) else [old]) or len(rows) != len(before["options"]) \
                    or [r.get("uid") for r in rows] != [r["uid"] for r in before["options"]]:
                step["correct"] = right[0] if len(right) == 1 else right
            old_expl = original.get("explanations") or []
            if old_expl or any(r.get("explanation_title") or r.get("explanation_text") for r in rows):
                before_rows = {r["uid"]: r for r in before["options"]}
                explanations = []
                for row in rows:
                    uid = row.get("uid")
                    base = _base_rows(old_expl, uid) or {}
                    old_row = before_rows.get(uid) if uid is not None else None
                    _put(base, "title", row.get("explanation_title", ""), (old_row or {}).get("explanation_title"))
                    _put(base, "text", row.get("explanation_text", ""), (old_row or {}).get("explanation_text"))
                    explanations.append({"title": base.pop("title", ""), "text": base.pop("text", ""), **base})
                step["explanations"] = explanations
        cls._common_into(step, data, before)


class TriageSerializer(StepSerializer):
    type = "triage"
    skeleton = {"title": "", "live_tag": "", "alerts": [], "levels": [], "correct": 0, "feedback": {}}
    ROW = ("from", "time", "msg")

    @classmethod
    def from_json(cls, step):
        levels = step.get("levels") or []
        return {
            "title": _text(step, "title"),
            "live_tag": _text(step, "live_tag"),
            "alerts": [{"uid": i, **_texts_from(a, cls.ROW)} for i, a in enumerate(step.get("alerts") or [])],
            "severity": step.get("correct"),
            "levels": [_text(level, "label") for level in levels],   # shown, not edited
            **cls._common_from(step),
        }

    @classmethod
    def write(cls, step, data, before, original):
        from ..conversion import SEVERITY
        _put(step, "title", data["title"], before["title"])
        _put(step, "live_tag", data["live_tag"], before["live_tag"])
        if not step.get("levels"):
            step["levels"] = [{"label": label, "desc": desc, "dot": dot} for _, label, desc, dot in SEVERITY]

        def alert(base, row, old, position):
            _fields_into(base, row, old, cls.ROW)
            if old is None or row.get("from") != old.get("from") or "ini" not in base:
                base["ini"] = _initials(row.get("from", ""))
            if "bg" not in base:
                base["bg"] = ALERT_COLOURS[position % len(ALERT_COLOURS)]
            return base
        step["alerts"] = _merge_rows(original.get("alerts") or [], before["alerts"], data["alerts"], alert)
        if data["severity"] != before["severity"]:
            step["correct"] = data["severity"]
        cls._common_into(step, data, before)


class OrderSerializer(StepSerializer):
    """The admin lists the steps in the right order; students get them shuffled."""
    type = "order"
    skeleton = {"title": "", "items": [], "correct": [], "feedback": {}}

    @classmethod
    def from_json(cls, step):
        by_id = {str(item["id"]): item for item in step.get("items") or []}
        return {
            "title": _text(step, "title"),
            "steps": [{"uid": i, "text": _text(by_id.get(str(i)), "text")} for i in step.get("correct") or []],
            **cls._common_from(step),
        }

    @staticmethod
    def shuffled(ids):
        """A stable shuffle (same ids, same order every save) that never matches the answer."""
        out = list(ids)
        random.Random("|".join(map(str, ids))).shuffle(out)
        if len(out) > 1 and out == list(ids):
            out = out[1:] + out[:1]
        return out

    @classmethod
    def write(cls, step, data, before, original):
        _put(step, "title", data["title"], before["title"])
        if data["steps"] != before["steps"]:
            items = {str(item["id"]): item for item in original.get("items") or []}
            taken = set(items)
            ids, texts = [], {}
            for row in data["steps"]:
                uid = row.get("uid")
                item_id = uid if uid is not None and str(uid) in items else _new_id("s", taken)
                ids.append(item_id)
                texts[str(item_id)] = row.get("text", "")
            original_ids = [item["id"] for item in original.get("items") or []]
            if sorted(map(str, ids)) == sorted(map(str, original_ids)):
                shown = original_ids                      # same steps: keep the students' order
            else:
                shown = cls.shuffled(ids)
            new_items = []
            for item_id in shown:
                item = copy.deepcopy(items.get(str(item_id), {"id": item_id}))
                item["text"] = texts[str(item_id)]
                new_items.append(item)
            step["items"] = new_items
            step["correct"] = ids
        cls._common_into(step, data, before)


class MatchSerializer(StepSerializer):
    """Problem -> fix pairs; the right-hand column is shown shifted so pairs never line up."""
    type = "match"
    skeleton = {"eyebrow": "", "left_label": "", "right_label": "", "left": [], "right": [], "correct": [], "feedback": {}}

    @classmethod
    def from_json(cls, step):
        left = {str(i["id"]): i for i in step.get("left") or []}
        right = {str(i["id"]): i for i in step.get("right") or []}
        return {
            "eyebrow": _text(step, "eyebrow"),
            "left_label": _text(step, "left_label"),
            "right_label": _text(step, "right_label"),
            "pairs": [{"uid": l_id, "right_uid": r_id, "left": _text(left.get(str(l_id)), "text"),
                       "right": _text(right.get(str(r_id)), "text")} for l_id, r_id in step.get("correct") or []],
            **cls._common_from(step),
        }

    @classmethod
    def write(cls, step, data, before, original):
        for key in ("eyebrow", "left_label", "right_label"):
            _put(step, key, data[key], before[key])
        if data["pairs"] != before["pairs"]:
            left = {str(i["id"]): i for i in original.get("left") or []}
            right = {str(i["id"]): i for i in original.get("right") or []}
            taken_l, taken_r = set(left), set(right)
            pairs, left_text, right_text = [], {}, {}
            for row in data["pairs"]:
                l_id = row.get("uid") if row.get("uid") is not None and str(row.get("uid")) in left else _new_id("l", taken_l)
                r_id = (row.get("right_uid") if row.get("right_uid") is not None and str(row.get("right_uid")) in right
                        else _new_id("r", taken_r))
                pairs.append([l_id, r_id])
                left_text[str(l_id)], right_text[str(r_id)] = row.get("left", ""), row.get("right", "")

            def column(old_items, by_id, ids, texts, shift):
                old_ids = [i["id"] for i in old_items]
                if sorted(map(str, ids)) == sorted(map(str, old_ids)):
                    order = old_ids
                else:
                    order = ids[1:] + ids[:1] if shift and len(ids) > 1 else list(ids)
                out = []
                for item_id in order:
                    item = copy.deepcopy(by_id.get(str(item_id), {"id": item_id}))
                    item["text"] = texts[str(item_id)]
                    out.append(item)
                return out
            step["left"] = column(original.get("left") or [], left, [p[0] for p in pairs], left_text, False)
            step["right"] = column(original.get("right") or [], right, [p[1] for p in pairs], right_text, True)
            step["correct"] = pairs
        cls._common_into(step, data, before)


class BranchSerializer(StepSerializer):
    type = "branch"
    skeleton = {"scenes": [], "endings": {}}
    SCENE = ("title", "time", "tip")
    MSG = ("from", "addr", "text")
    ENDING = ("tag", "title", "text", "face")

    @classmethod
    def from_json(cls, step):
        endings = step.get("endings") or {}
        return {
            "meter_labels": _texts_from(step.get("meter_labels"), ("sec", "trust")),
            "scenes": [
                {"uid": i, **_texts_from(sc, cls.SCENE),
                 "messages": [{"uid": j, **_texts_from(m, cls.MSG)} for j, m in enumerate(sc.get("msgs") or [])],
                 "choices": [{"uid": j, "text": _text(c, "text"), "quality": _text(c.get("effects"), "kind"),
                              "outcome": _text(c.get("effects"), "out")} for j, c in enumerate(sc.get("choices") or [])]}
                for i, sc in enumerate(step.get("scenes") or [])
            ],
            "endings": {key: _texts_from(endings.get(key), cls.ENDING) for key in ("best", "mid", "bad")},
        }

    @classmethod
    def write(cls, step, data, before, original):
        _texts_into(step, "meter_labels", data["meter_labels"], before["meter_labels"])

        def message(base, row, old, position):
            _fields_into(base, row, old, cls.MSG)
            if old is None or row.get("from") != old.get("from") or "ini" not in base:
                base["ini"] = _initials(row.get("from", ""))
            if "bg" not in base:
                base["bg"] = ALERT_COLOURS[position % len(ALERT_COLOURS)]
            return base

        def choice(base, row, old, _pos):
            _put(base, "text", row.get("text", ""), (old or {}).get("text"))
            effects = base.get("effects") or {}
            quality = row.get("quality") or "meh"
            if old is None or quality != old.get("quality") or "sec" not in effects:
                sec, trust = DEFAULT_EFFECTS.get(quality, DEFAULT_EFFECTS["meh"])
                effects.update({"sec": sec, "trust": trust, "kind": quality})
            if old is None or row.get("outcome") != old.get("outcome"):
                effects["out"] = row.get("outcome", "")
            base["effects"] = effects
            return base

        def scene(base, row, old, _pos):
            _fields_into(base, row, old, cls.SCENE)
            base["msgs"] = _merge_rows(base.get("msgs") or [], (old or {}).get("messages") or [], row.get("messages") or [], message)
            base["choices"] = _merge_rows(base.get("choices") or [], (old or {}).get("choices") or [], row.get("choices") or [], choice)
            return base
        if data["scenes"] != before["scenes"]:
            step["scenes"] = _merge_rows(original.get("scenes") or [], before["scenes"], data["scenes"], scene)
        if data["endings"] != before["endings"]:
            endings = copy.deepcopy(step.get("endings") or {})
            for key in ("best", "mid", "bad"):
                _texts_into(endings, key, data["endings"][key], before["endings"][key])
            step["endings"] = endings


SERIALIZERS = {cls.type: cls for cls in (
    StorySerializer, ConceptCardsSerializer, HotspotSerializer, ConfigureSerializer, McqSerializer,
    TriageSerializer, OrderSerializer, MatchSerializer, BranchSerializer,
)}


class DebriefSerializer:
    """The results screen: headline, one-line summary, and what the learner practised."""

    @staticmethod
    def from_json(debrief):
        return {"headline": _text(debrief, "headline"), "sub": _text(debrief, "sub"),
                "learned": list((debrief or {}).get("learned") or [])}

    @classmethod
    def to_json(cls, data, original=None):
        out = copy.deepcopy(original or {})
        before = cls.from_json(original)
        _put(out, "headline", data["headline"], before["headline"])
        _put(out, "sub", data["sub"], before["sub"])
        if data["learned"] != before["learned"]:
            out["learned"] = [line for line in data["learned"] if line]
        return out


class MetaSerializer:
    """Badge name and short description (content["meta"]); ignored by the player for now."""
    KEYS = ("badge", "description")

    @classmethod
    def from_json(cls, meta):
        return _texts_from(meta, cls.KEYS)

    @classmethod
    def to_json(cls, data, original=None):
        out = copy.deepcopy(original or {})
        before = cls.from_json(original)
        for key in cls.KEYS:
            _put(out, key, data[key], before[key])
        return out


class SessionSerializer:
    """A whole scenario's content: the steps in order, the results screen and the meta block.
    Top-level keys the studio doesn't edit (e.g. `source`, future keys) are kept as they are."""

    @staticmethod
    def from_json(content):
        content = content or {}
        return {
            "steps": [{"uid": i, "type": s["type"], "data": SERIALIZERS[s["type"]].from_json(s)}
                      for i, s in enumerate(content.get("steps") or [])],
            "debrief": DebriefSerializer.from_json(content.get("debrief")),
            "meta": MetaSerializer.from_json(content.get("meta")),
        }

    @classmethod
    def to_json(cls, data, original=None):
        original = original or {}
        out = copy.deepcopy(original)
        old_steps = original.get("steps") or []
        before = cls.from_json(original)
        before_steps = {s["uid"]: s for s in before["steps"]}
        steps = []
        for row in data["steps"]:
            uid = row.get("uid")
            base = _base_rows(old_steps, uid)
            if base is not None and base["type"] == row["type"]:
                if row["data"] == before_steps[uid]["data"]:
                    steps.append(base)                   # untouched step: exactly as stored
                else:
                    steps.append(SERIALIZERS[row["type"]].to_json(row["data"], base))
            else:
                steps.append(SERIALIZERS[row["type"]].to_json(row["data"]))
        cls._relabel(steps, data["steps"], before["steps"])
        out["steps"] = steps
        if data["debrief"] != before["debrief"]:
            out["debrief"] = DebriefSerializer.to_json(data["debrief"], original.get("debrief"))
        if data["meta"] != before["meta"]:
            meta = MetaSerializer.to_json(data["meta"], original.get("meta"))
            if meta:
                out["meta"] = meta
            else:
                out.pop("meta", None)
        return out

    @staticmethod
    def _relabel(steps, rows, before_rows):
        """The briefing lists the later steps by name. Kept as written while the step list is
        unchanged; rebuilt (reusing each kept step's old label) when steps move, come or go."""
        if not steps or steps[0]["type"] != "story":
            return
        order = [(r.get("uid"), r["type"]) for r in rows[1:]]
        old_order = [(r["uid"], r["type"]) for r in before_rows[1:]]
        if order == old_order:
            return
        old_labels = list(steps[0].get("labels") or [])
        reuse = len(old_labels) == len(old_order)
        old_index = {uid: i for i, (uid, _) in enumerate(old_order)}
        labels = []
        for uid, kind in order:
            if reuse and uid in old_index and old_order[old_index[uid]][1] == kind:
                labels.append(old_labels[old_index[uid]])
            else:
                labels.append(DEFAULT_LABELS.get(kind, kind.replace("_", " ").title()))
        steps[0]["labels"] = labels
