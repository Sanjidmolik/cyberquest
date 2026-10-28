"""Practice Studio, phase 2: form data <-> scenario JSON.

Round trips are compared as canonical JSON (the same spelling the seed fingerprint uses), over
every real session in the seed sources, the design samples and the three starter templates."""

import copy
import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from practice.conversion import convert
from practice.graders import FLOWS, validate_content, validate_step
from practice.scenarios import SCENARIOS
from practice.seeding import canonical_json
from practice.studio.serializers import (
    DEFAULT_EFFECTS, SERIALIZERS, DebriefSerializer, MetaSerializer, OrderSerializer, SessionSerializer,
)
from practice.studio.starter_templates import KINDS, all_templates

BASE = Path(settings.BASE_DIR)


def real_sessions():
    """(name, kind, content) for every session the seed commands write, the samples and the templates."""
    rows = [(f"convert:{key}", data["kind"], data["content"]) for key, data in
            ((key, convert(old)) for key, old in SCENARIOS.items())]
    for path in sorted((BASE / "practice" / "scenario_content").glob("*.json")) + \
            sorted((BASE / "docs" / "practice-redesign" / "samples").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        rows.append((path.name, data["kind"], data["content"]))
    rows += [(f"template:{kind}", data["kind"], data["content"]) for kind, data in all_templates().items()]
    return rows


SESSIONS = real_sessions()


def steps_of(kind):
    return [(name, i, step) for name, _, content in SESSIONS for i, step in enumerate(content["steps"])
            if step["type"] == kind]


def same(a, b):
    return canonical_json(a) == canonical_json(b)


def changed_paths(a, b, path=""):
    """Every leaf path where a and b differ (lists compared position by position)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = set()
        for key in set(a) | set(b):
            out |= changed_paths(a.get(key, KeyError), b.get(key, KeyError), f"{path}.{key}" if path else str(key))
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = set()
        for i, (x, y) in enumerate(zip(a, b)):
            out |= changed_paths(x, y, f"{path}.{i}" if path else str(i))
        return out
    return set() if a == b else {path}


class CoverageTests(SimpleTestCase):
    def test_the_sources_cover_every_step_type(self):
        self.assertGreaterEqual(len(SESSIONS), 33 + 1 + 2 + 3)
        used = {step["type"] for _, _, content in SESSIONS for step in content["steps"]}
        self.assertEqual(used, set(SERIALIZERS))

    def test_every_template_passes_validate_content_with_its_recipe(self):
        recipes = {
            "simulation": ["story", "concept_cards", "hotspot", "configure", "match"],
            "incident": ["story", "triage", "hotspot", "mcq", "order"],
            "choice": ["story", "branch"],
        }
        for kind, data in all_templates().items():
            self.assertEqual(data["kind"], kind)
            self.assertEqual(list(FLOWS[kind]), recipes[kind])
            self.assertEqual([s["type"] for s in data["content"]["steps"]], recipes[kind])
            if kind == "choice":                                    # 3 scenes x 3 choices
                scenes = data["content"]["steps"][1]["scenes"]
                self.assertEqual([len(scene["choices"]) for scene in scenes], [3, 3, 3])
            validate_content(kind, data["content"])
            self.assertIsNone(data["time_limit_sec"])               # no timers in Practice
            self.assertEqual(data["xp_reward"], 50)                 # the practice XP rule
            self.assertTrue(data["content"]["meta"]["badge"])
        self.assertEqual(tuple(all_templates()), KINDS)


class RoundTripTests(SimpleTestCase):
    def test_every_step_round_trips_exactly(self):
        for name, _, content in SESSIONS:
            for index, step in enumerate(content["steps"]):
                serializer = SERIALIZERS[step["type"]]
                again = serializer.to_json(serializer.from_json(step), step)
                self.assertTrue(same(again, step), f"{name} step {index} ({step['type']})")
                self.assertTrue(same(serializer.from_json(again), serializer.from_json(step)))

    def test_every_session_round_trips_exactly(self):
        for name, _, content in SESSIONS:
            again = SessionSerializer.to_json(SessionSerializer.from_json(content), content)
            self.assertTrue(same(again, content), name)

    def test_debrief_and_meta_round_trip(self):
        for name, _, content in SESSIONS:
            self.assertTrue(same(DebriefSerializer.to_json(DebriefSerializer.from_json(content["debrief"]),
                                                           content["debrief"]), content["debrief"]), name)
            meta = content.get("meta") or {}
            self.assertTrue(same(MetaSerializer.to_json(MetaSerializer.from_json(meta), meta), meta), name)

    def test_keys_the_form_does_not_show_survive_an_edit(self):
        """Unknown keys at every level (top level, meta, step, row, nested group) are kept."""
        for name, kind, content in SESSIONS:
            future = copy.deepcopy(content)
            future["future_top"] = {"x": 1}
            future["meta"] = {**future.get("meta", {}), "future_meta": [1, 2]}
            for step in future["steps"]:
                step["future_step"] = "kept"
                for value in step.values():
                    if isinstance(value, list) and value and isinstance(value[0], dict):
                        value[0]["future_row"] = True
                if isinstance(step.get("feedback"), dict):
                    step["feedback"]["future_fb"] = "kept"
            data = SessionSerializer.from_json(future)
            data["debrief"]["sub"] += " (edited)"
            for row in data["steps"]:                     # touch every step, so each one is re-merged
                body = row["data"]
                key = next(k for k in ("title", "intro", "eyebrow", "left_label") if k in body) \
                    if row["type"] != "branch" else None
                if key:
                    body[key] = (body[key] or "") + " (edited)"
                else:
                    body["meter_labels"]["sec"] += " (edited)"
            again = SessionSerializer.to_json(data, future)
            self.assertEqual(again["future_top"], {"x": 1}, name)
            self.assertEqual(again["meta"]["future_meta"], [1, 2], name)
            for old, new in zip(future["steps"], again["steps"]):
                self.assertEqual(new["future_step"], "kept", name)
                for key, value in old.items():
                    if isinstance(value, list) and value and isinstance(value[0], dict) and "future_row" in value[0]:
                        self.assertTrue(new[key][0].get("future_row"), f"{name} {old['type']}.{key}")
                if "future_fb" in (old.get("feedback") or {}):
                    self.assertEqual(new["feedback"]["future_fb"], "kept", name)
            validate_content(kind, {k: v for k, v in again.items() if k != "future_top"})


class SingleEditTests(SimpleTestCase):
    """Editing one field in the form changes exactly that field in the step, nothing else."""

    def _check(self, kind, edit, expected):
        cases = steps_of(kind)
        self.assertTrue(cases, kind)
        for name, index, step in cases:
            data = SERIALIZERS[kind].from_json(step)
            edit(data)
            after = SERIALIZERS[kind].to_json(data, step)
            want = expected(step) if callable(expected) else expected
            self.assertEqual(changed_paths(step, after), want, f"{name} step {index}")
            validate_step(after)

    def test_story(self):
        self._check("story", lambda d: d.update(intro=d["intro"] + " (edited)"), {"intro"})
        self._check("story", lambda d: d.update(mood="surprised"),
                    lambda s: set() if s["end_expression"] == "surprised" else {"end_expression"})

    def test_concept_cards(self):
        self._check("concept_cards", lambda d: d["cards"][1].update(back=d["cards"][1]["back"] + "!"), {"cards.1.back"})

    def test_hotspot(self):
        self._check("hotspot", lambda d: d["items"][0].update(value=d["items"][0]["value"] + "!"), {"items.0.value"})
        self._check("hotspot", lambda d: d["feedback"]["good"].update(text="Well spotted."), {"feedback.good.text"})

    def test_configure(self):
        self._check("configure", lambda d: d["settings"][0].update(hint="New hint"), {"settings.0.hint"})
        self._check("configure", lambda d: d["settings"][0].update(threat="Renamed threat"), {"threats.0.label"})

    def test_mcq(self):
        self._check("mcq", lambda d: d["options"][2].update(text=d["options"][2]["text"] + "!"), {"options.2"})
        self._check("mcq", lambda d: d.update(question="What now?"), {"tips.start"})

    def test_triage(self):
        self._check("triage", lambda d: d["alerts"][0].update(msg=d["alerts"][0]["msg"] + "!"), {"alerts.0.msg"})
        self._check("triage", lambda d: d.update(title="Rate it"), {"title"})

    def test_order(self):
        def where(step):
            first = step["correct"][0]
            return {f"items.{[i['id'] for i in step['items']].index(first)}.text"}
        self._check("order", lambda d: d["steps"][0].update(text=d["steps"][0]["text"] + "!"), where)

    def test_match(self):
        def where(step):
            right_id = step["correct"][0][1]
            return {f"right.{[i['id'] for i in step['right']].index(right_id)}.text"}
        self._check("match", lambda d: d["pairs"][0].update(right=d["pairs"][0]["right"] + "!"), where)

    def test_branch(self):
        self._check("branch", lambda d: d["scenes"][0]["choices"][1].update(outcome="It went fine."),
                    {"scenes.0.choices.1.effects.out"})
        self._check("branch", lambda d: d["endings"]["mid"].update(title="So-so"), {"endings.mid.title"})

    def test_session_debrief_and_meta(self):
        for name, _, content in SESSIONS:
            data = SessionSerializer.from_json(content)
            data["debrief"]["sub"] = "Edited summary"
            data["meta"]["badge"] = "Edited badge"
            after = SessionSerializer.to_json(data, content)
            expected = {"debrief.sub", "meta.badge"} if content.get("meta") else {"debrief.sub", "meta"}
            self.assertEqual(changed_paths(content, after), expected, name)


class DerivedValueTests(SimpleTestCase):
    """Values the admin never types: answers from ticks and radios, ids, shuffles, effects."""

    def test_ticking_a_clue_sets_the_answer_and_how_many_to_find(self):
        for name, index, step in steps_of("hotspot"):
            data = SERIALIZERS["hotspot"].from_json(step)
            spare = next((r for r in data["items"] if not r["clue"]), None)
            if spare is None:
                continue
            spare["clue"] = True
            after = SERIALIZERS["hotspot"].to_json(data, step)
            self.assertEqual(sorted(after["correct"]), sorted(step["correct"] + [spare["uid"]]), name)
            self.assertEqual(after["select"], len(step["correct"]) + 1)
            self.assertEqual(changed_paths(step, after), {"correct", "select"}, name)

    def test_order_is_entered_in_the_right_order_and_shuffled_for_students(self):
        steps = [{"uid": None, "text": t} for t in ("Isolate", "Rotate keys", "Notify", "Review")]
        built = OrderSerializer.to_json({"title": "Put it in order", "steps": steps,
                                         "tips": {k: "" for k in ("start", "progress", "ready", "good", "bad")},
                                         "feedback": {"good": {"title": "Yes", "text": ""}, "bad": {"title": "No", "text": ""}}})
        by_id = {i["id"]: i["text"] for i in built["items"]}
        self.assertEqual([by_id[i] for i in built["correct"]], ["Isolate", "Rotate keys", "Notify", "Review"])
        self.assertNotEqual([i["id"] for i in built["items"]], built["correct"])           # shuffled
        again = OrderSerializer.to_json(OrderSerializer.from_json(built), built)
        self.assertTrue(same(again, built))                                                  # and stable
        validate_step(built)

    def test_new_match_pair_gets_ids_and_the_right_column_never_lines_up(self):
        for name, index, step in steps_of("match"):
            data = SERIALIZERS["match"].from_json(step)
            data["pairs"].append({"uid": None, "right_uid": None, "left": "New problem", "right": "New fix"})
            after = SERIALIZERS["match"].to_json(data, step)
            validate_step(after)
            self.assertEqual(len(after["correct"]), len(step["correct"]) + 1)
            right_order = [i["id"] for i in after["right"]]
            self.assertNotEqual(right_order, [p[1] for p in after["correct"]], name)

    def test_changing_a_choice_quality_sets_its_effects(self):
        for name, index, step in steps_of("branch"):
            data = SERIALIZERS["branch"].from_json(step)
            choice = data["scenes"][0]["choices"][0]
            new_quality = "good" if choice["quality"] != "good" else "bad"
            choice["quality"] = new_quality
            after = SERIALIZERS["branch"].to_json(data, step)
            effects = after["scenes"][0]["choices"][0]["effects"]
            self.assertEqual((effects["kind"], effects["sec"], effects["trust"]),
                             (new_quality, *DEFAULT_EFFECTS[new_quality]))
            self.assertEqual(effects["out"], step["scenes"][0]["choices"][0]["effects"]["out"])
            validate_step(after)

    def test_a_second_right_answer_makes_the_mcq_accept_either(self):
        for name, index, step in steps_of("mcq"):
            data = SERIALIZERS["mcq"].from_json(step)
            for row in data["options"]:
                row["correct"] = row["uid"] in (0, 1)
            after = SERIALIZERS["mcq"].to_json(data, step)
            self.assertEqual(after["correct"], [0, 1], name)
            validate_step(after)

    def test_new_configure_setting_gets_a_key_points_and_its_threat(self):
        for name, index, step in steps_of("configure"):
            data = SERIALIZERS["configure"].from_json(step)
            data["settings"].append({"uid": None, "label": "Audit log", "hint": "Who did what",
                                     "threat": "Silent tampering", "options": ["Off", "Weekly", "Always"], "secure": 2})
            after = SERIALIZERS["configure"].to_json(data, step)
            new = after["settings"][-1]
            self.assertEqual((new["key"], new["points"], new["secure"]), ("audit_log", [0, 10, 30], 2))
            self.assertIn({"label": "Silent tampering", "settings": ["audit_log"]}, after["threats"])
            self.assertEqual(after["threats"][:len(step["threats"])], step["threats"])     # others untouched
            validate_step(after)

    def test_renamed_triage_sender_gets_new_initials(self):
        for name, index, step in steps_of("triage"):
            data = SERIALIZERS["triage"].from_json(step)
            data["alerts"][0]["from"] = "Priya Nair"
            after = SERIALIZERS["triage"].to_json(data, step)
            self.assertEqual(changed_paths(step, after), {"alerts.0.from", "alerts.0.ini"} - (
                {"alerts.0.ini"} if step["alerts"][0]["ini"] == "PN" else set()), name)
            self.assertEqual(after["alerts"][0]["ini"], "PN")

    def test_every_template_step_can_be_built_from_form_data_alone(self):
        """A brand-new session typed into the forms (no original JSON) is valid."""
        for kind, template in all_templates().items():
            data = SessionSerializer.from_json(template["content"])
            for row in data["steps"]:
                row["uid"] = None                                 # as if added in the studio
            built = SessionSerializer.to_json(data)
            validate_content(kind, built)
            self.assertEqual([s["type"] for s in built["steps"]], [s["type"] for s in template["content"]["steps"]])
            self.assertEqual(built["meta"], template["content"]["meta"])

    def test_briefing_labels_follow_the_steps_only_when_they_change(self):
        template = all_templates()["incident"]["content"]
        labels = template["steps"][0]["labels"]
        data = SessionSerializer.from_json(template)
        self.assertEqual(SessionSerializer.to_json(data, template)["steps"][0]["labels"], labels)
        data["steps"].pop(4)                                      # remove the order step
        self.assertEqual(SessionSerializer.to_json(data, template)["steps"][0]["labels"], labels[:3])
