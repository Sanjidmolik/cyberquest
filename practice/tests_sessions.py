"""Interactive practice sessions: graders, answer stripping, loader, API flow and page wiring."""

import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from courses.models import Course
from practice import graders
from practice.graders import ANSWER_KEYS, InvalidAnswer, public_content
from practice.models import Attempt, Scenario, StepAnswer
from practice.seeding import content_hash

User = get_user_model()


def _keys(value):
    """Every dict key anywhere in a JSON-like value."""
    if isinstance(value, dict):
        found = set(value)
        for v in value.values():
            found |= _keys(v)
        return found
    if isinstance(value, list):
        found = set()
        for v in value:
            found |= _keys(v)
        return found
    return set()


# The two design samples (configure / order / triage flows) live with the design docs now.
SAMPLES = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "docs" / "practice-redesign" / "samples")


def _load():
    call_command("load_scenarios", stdout=StringIO())
    call_command("load_scenarios", dir=SAMPLES, stdout=StringIO())


def _make_courses():
    Course.objects.create(code="MOD-01", title="Phishing & Scam Prevention", short_description="x", order=20)
    Course.objects.create(code="MOD-04", title="Cryptography", short_description="x", order=900, is_coming_soon=True)
    Course.objects.create(code="MOD-06", title="OSINT", short_description="x", order=920, is_coming_soon=True)


class GraderTests(TestCase):
    """One grader test per step type (correct, wrong and malformed answers)."""

    def test_hotspot(self):
        step = {"type": "hotspot", "items": [{}] * 5, "correct": [1, 2, 3], "feedback": {"good": {"title": "Yes"}}}
        self.assertTrue(graders.grade_hotspot(step, [3, 1, 2])["correct"])
        res = graders.grade_hotspot(step, [0, 1, 2])
        self.assertFalse(res["correct"])
        self.assertEqual(res["reveal"]["correct"], [1, 2, 3])
        with self.assertRaises(InvalidAnswer):
            graders.grade_hotspot(step, [9])

    def test_configure(self):
        step = {"type": "configure", "settings": [
            {"key": "cipher", "options": ["DES", "3DES", "AES"], "secure": 2, "points": [0, 10, 50]},
            {"key": "expiry", "options": ["Never", "7 days"], "secure": 1, "points": [0, 50]},
        ], "threats": [{"label": "t1", "settings": ["cipher"]}, {"label": "t2", "settings": ["cipher", "expiry"]}]}
        ok = graders.grade_configure(step, {"cipher": 2, "expiry": 1})
        self.assertTrue(ok["correct"])
        self.assertEqual(ok["reveal"]["score"], 100)
        self.assertEqual(ok["reveal"]["threats"], [2, 2])
        weak = graders.grade_configure(step, {"cipher": 1, "expiry": 0})
        self.assertFalse(weak["correct"])
        self.assertEqual(weak["reveal"]["threats"], [1, 1])
        with self.assertRaises(InvalidAnswer):
            graders.grade_configure(step, {"cipher": 2})

    def test_mcq(self):
        step = {"type": "mcq", "options": ["a", "b", "c"], "correct": 1}
        self.assertTrue(graders.grade_mcq(step, 1)["correct"])
        self.assertFalse(graders.grade_mcq(step, 0)["correct"])
        for bad in (True, "1", 7, None):
            with self.assertRaises(InvalidAnswer):
                graders.grade_mcq(step, bad)

    def test_triage(self):
        step = {"type": "triage", "levels": [{}] * 4, "correct": 2}
        self.assertTrue(graders.grade_triage(step, 2)["correct"])
        self.assertFalse(graders.grade_triage(step, 3)["correct"])

    def test_order(self):
        step = {"type": "order", "items": [{"id": "a"}, {"id": "b"}, {"id": "c"}], "correct": ["b", "a", "c"]}
        self.assertTrue(graders.grade_order(step, ["b", "a", "c"])["correct"])
        self.assertFalse(graders.grade_order(step, ["a", "b", "c"])["correct"])
        with self.assertRaises(InvalidAnswer):
            graders.grade_order(step, ["a", "a", "c"])

    def test_match(self):
        step = {"type": "match", "left": [{"id": "x"}, {"id": "y"}], "right": [{"id": "1"}, {"id": "2"}],
                "correct": [["x", "2"], ["y", "1"]]}
        self.assertTrue(graders.grade_match(step, [["y", "1"], ["x", "2"]])["correct"])
        res = graders.grade_match(step, [["x", "1"], ["y", "2"]])
        self.assertFalse(res["correct"])
        self.assertEqual(res["reveal"]["pairs"], [["x", "1", False], ["y", "2", False]])
        with self.assertRaises(InvalidAnswer):
            graders.grade_match(step, [["x", "1"]])

    def test_branch_effects_and_endings(self):
        def choice(kind, sec):
            return {"text": kind, "effects": {"sec": sec, "trust": 0, "kind": kind, "out": kind + " happened"}}
        scene = {"choices": [choice("bad", -30), choice("meh", -10), choice("good", 25)]}
        step = {"type": "branch", "scenes": [scene, scene, scene], "endings": {
            "best": {"title": "Best"}, "mid": {"title": "Mid"}, "bad": {"title": "Bad"}}}

        state = {}
        for n in range(3):
            res, state = graders.grade_branch(step, {"scene": n, "choice": 2}, state)
        self.assertEqual(res["ending"]["key"], "best")
        self.assertEqual(state["meters"]["sec"], 100)          # clamped
        self.assertIsNone(res["next_scene"])

        state = {}
        res, state = graders.grade_branch(step, {"scene": 0, "choice": 0}, state)
        self.assertEqual((res["effects"]["kind"], res["next_scene"], res["meters"]["sec"]), ("bad", 1, 20))
        res, state = graders.grade_branch(step, {"scene": 1, "choice": 0}, state)
        res, state = graders.grade_branch(step, {"scene": 2, "choice": 2}, state)
        self.assertEqual(res["ending"]["key"], "bad")

        with self.assertRaises(InvalidAnswer):  # scenes must be answered in order
            graders.grade_branch(step, {"scene": 2, "choice": 0}, {"scene": 0})


class LoaderAndStrippingTests(TestCase):
    def setUp(self):
        _make_courses()
        _load()

    def test_loads_three_samples_onto_existing_courses(self):
        self.assertEqual(
            {s.slug: (s.kind, s.topic.code) for s in Scenario.objects.all()},
            {"crypto-01-simulation": ("simulation", "MOD-04"), "crypto-04-incident": ("incident", "MOD-04"),
             "phish-01-choice": ("choice", "MOD-01")},
        )
        self.assertTrue(all(s.time_limit_sec is None for s in Scenario.objects.all()))

    def test_loader_is_idempotent_and_bumps_version_on_change(self):
        out = StringIO()
        call_command("load_scenarios", stdout=out)
        self.assertIn("0 created, 0 updated, 1 unchanged", out.getvalue())   # phish-01-choice
        scenario = Scenario.objects.get(slug="phish-01-choice")
        scenario.content = {"steps": []}
        scenario.content_hash = content_hash(scenario.content)  # an older seed, not a hand edit
        scenario.save()
        call_command("load_scenarios", stdout=StringIO())
        scenario.refresh_from_db()
        self.assertEqual(scenario.version, 2)
        self.assertTrue(scenario.content["steps"])

    def test_content_sent_to_client_has_no_answers(self):
        for scenario in Scenario.objects.all():
            self.assertTrue(_keys(scenario.content) & ANSWER_KEYS, scenario.slug)  # the source has answers…
            self.assertFalse(_keys(public_content(scenario.content)) & ANSWER_KEYS, scenario.slug)  # …the copy does not

        user = User.objects.create_user(email="peek@example.com", password="testpass123", username="peek")
        self.client.force_login(user)
        for slug in ("crypto-01-simulation", "crypto-04-incident", "phish-01-choice"):
            res = self.client.post(reverse("practice:api_start"), json.dumps({"scenario": slug}), content_type="application/json")
            self.assertEqual(res.status_code, 201)
            payload = res.json()
            self.assertFalse(_keys(payload) & ANSWER_KEYS, slug)
            raw = res.content.decode()
            for leak in ("The weak spots were the encryption", "That makes it High", "The codes are gone", "Threat contained"):
                self.assertNotIn(leak, raw)                # feedback, outcomes and endings stay on the server
            page = self.client.get(reverse("practice:session", args=[slug]))
            self.assertFalse(_keys(page.context["session_config"]) & ANSWER_KEYS)
            self.assertNotIn('"correct"', page.content.decode())


class SessionApiTests(TestCase):
    def setUp(self):
        _make_courses()
        _load()
        self.user = User.objects.create_user(email="learner@example.com", password="testpass123", username="learner")
        self.client.force_login(self.user)

    def post(self, name, body=None, *args):
        return self.client.post(reverse(name, args=args), json.dumps(body or {}), content_type="application/json")

    def start(self, slug):
        res = self.post("practice:api_start", {"scenario": slug})
        self.assertEqual(res.status_code, 201)
        return res.json()["attempt_id"]

    def answer(self, attempt_id, step, answer):
        return self.post("practice:api_answer", {"step": step, "answer": answer, "time_ms": 1200}, attempt_id)

    def test_simulation_flow_awards_xp_once(self):
        aid = self.start("crypto-01-simulation")
        self.assertEqual(self.answer(aid, 0, None).status_code, 400)            # the briefing has no answer
        self.assertEqual(self.answer(aid, 1, {"flipped": 3}).json()["correct"], None)
        wrong = self.answer(aid, 2, [0, 1, 2]).json()
        self.assertEqual((wrong["correct"], wrong["hearts"], wrong["title"]), (False, 2, "Not quite"))
        self.assertEqual(self.answer(aid, 2, [1, 2, 3]).status_code, 409)       # no second try at a graded step
        self.assertEqual(self.post("practice:api_complete", None, aid).status_code, 400)  # steps left
        ok = self.answer(aid, 3, {"cipher": 2, "keyd": 2, "access": 2, "expiry": 2}).json()
        self.assertTrue(ok["correct"])
        self.assertEqual(ok["reveal"]["score"], 100)
        match = self.answer(aid, 4, [["des", "aes"], ["key", "sep"], ["link", "named"]]).json()
        self.assertTrue(match["correct"])

        done = self.post("practice:api_complete", None, aid).json()
        self.assertEqual(done["xp"], 60)
        self.assertEqual(done["accuracy"], 67)                                   # 2 of 3 graded steps right
        self.assertEqual(done["competency"], {"course": "Cryptography", "done": 1, "total": 2, "percent": 50})
        self.assertEqual(done["next"]["url"], reverse("practice:session", args=["crypto-04-incident"]))
        self.user.refresh_from_db()
        self.assertEqual(self.user.xp, 60)
        again = self.post("practice:api_complete", None, aid).json()
        self.assertEqual(again["xp"], 60)
        self.user.refresh_from_db()
        self.assertEqual(self.user.xp, 60)                                       # completing twice pays once
        self.assertEqual(self.answer(aid, 4, []).status_code, 409)               # finished attempts are closed

    def test_skip_counts_as_miss_without_losing_a_heart(self):
        aid = self.start("crypto-04-incident")
        for step in (1, 2, 3, 4):
            res = self.answer(aid, step, {"skipped": True}).json()
            self.assertEqual((res["correct"], res["hearts"]), (False, 3))
            self.assertNotIn("reveal", res)
        done = self.post("practice:api_complete", None, aid).json()
        self.assertEqual((done["accuracy"], done["xp"], done["hearts"]), (0, 120, 3))

    def test_choice_flow_ending_and_badge(self):
        from achievements.models import Badge
        Badge.objects.update_or_create(code="phishing_practice", defaults={"name": "Phishing Drill", "description": "d", "is_active": True})
        aid = self.start("phish-01-choice")
        first = self.answer(aid, 1, {"scene": 0, "choice": 2}).json()
        self.assertEqual((first["effects"]["kind"], first["next_scene"], first["meters"]), ("good", 1, {"sec": 75, "trust": 60}))
        self.assertEqual(self.answer(aid, 1, {"scene": 0, "choice": 1}).status_code, 400)  # scene already played
        self.answer(aid, 1, {"scene": 1, "choice": 1})
        last = self.answer(aid, 1, {"scene": 2, "choice": 1}).json()
        self.assertEqual(last["ending"]["key"], "best")
        done = self.post("practice:api_complete", None, aid).json()
        self.assertEqual((done["good_calls"], done["accuracy"], done["outcome"], done["xp"]), (3, 100, "best", 50))
        self.assertEqual([b["name"] for b in done["badges"]], ["Phishing Drill"])  # existing badge rules
        self.assertEqual(StepAnswer.objects.filter(attempt_id=aid).count(), 3)

    def test_attempts_are_private_and_locked_courses_stay_locked(self):
        aid = self.start("phish-01-choice")
        other = User.objects.create_user(email="other@example.com", password="testpass123", username="other")
        self.client.force_login(other)
        self.assertEqual(self.answer(aid, 1, {"scene": 0, "choice": 0}).status_code, 404)
        self.assertEqual(self.post("practice:api_complete", None, aid).status_code, 404)

        osint = Scenario.objects.get(slug="phish-01-choice")
        osint.pk = None
        osint.slug = "osint-01-choice"
        osint.topic = Course.objects.get(code="MOD-06")
        osint.save()
        self.assertEqual(self.post("practice:api_start", {"scenario": "osint-01-choice"}).status_code, 403)
        page = self.client.get(reverse("practice:session", args=["osint-01-choice"]))
        self.assertContains(page, "Coming Soon")
        self.assertEqual(self.post("practice:api_start", {"scenario": "nope"}).status_code, 404)

    def test_session_page_and_center_links(self):
        page = self.client.get("/practice/crypto-04-incident/")
        self.assertEqual(page.status_code, 200)
        self.assertTemplateUsed(page, "practice/session.html")
        self.assertContains(page, "Certificate and TLS problem")
        self.assertContains(page, "CRYPTOGRAPHY · SCENARIO 2 OF 2")
        self.assertContains(page, "no timer")
        self.assertContains(page, 'id="cq-hana-tpl"')
        self.assertRedirects(self.client.get("/practice/phishing/"), "/practice/?topic=phishing")  # old topic page
        self.assertEqual(self.client.get("/practice/not-a-thing/").status_code, 404)

        center = self.client.get(reverse("practice:center"))
        self.assertContains(center, 'href="/practice/phish-01-choice/"')
        self.assertContains(center, 'href="/practice/crypto-01-simulation/"')
