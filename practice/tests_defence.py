"""Defence-course practice scenarios: coverage, full play-through, hints, learning summary, replay, no timers."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from practice.models import PracticeSession
from practice.scenarios import DOMAIN_BY_SLUG, SCENARIOS as SCENARIOS_BY_KEY, scenarios_for_domain

User = get_user_model()
NEW_TOPICS = ("safety", "malware", "device", "privacy", "response")


class DefenceScenarioDataTests(TestCase):
    def test_every_new_topic_has_distinct_valid_scenarios(self):
        seen_titles = set()
        for slug in NEW_TOPICS:
            self.assertIn(slug, DOMAIN_BY_SLUG)
            self.assertIn(slug, dict(PracticeSession.DOMAIN_CHOICES))
            rows = scenarios_for_domain(slug)
            self.assertGreaterEqual(len(rows), 2, slug)
            self.assertEqual({r["activity_type"] for r in rows}, {"simulation", "incident"}, slug)
            for s in rows:
                self.assertNotIn(s["title"], seen_titles)
                seen_titles.add(s["title"])
                self.assertEqual(s["workspace_type"], "panels")
                self.assertTrue(s["workspace"]["panels"])
                self.assertTrue(set(s["required_evidence"]) <= set(s["investigations"]))
                qualities = [d["quality"] for d in s["decisions"].values()]
                self.assertEqual(qualities.count("correct"), 1, s["key"])
                self.assertTrue(s.get("hint") and s.get("takeaways"), s["key"])
                for d in s["decisions"].values():
                    self.assertTrue(d["consequence"], s["key"])


class DefencePlayThroughTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="defender@example.com", password="testpass123", username="defender")
        self.client.login(email="defender@example.com", password="testpass123")

    def _start(self, domain, key):
        res = self.client.post(reverse("practice:start", args=[domain]), {"scenario_key": key})
        self.assertEqual(res.status_code, 302)
        return PracticeSession.objects.filter(user=self.user, scenario_key=key).latest("pk")

    def test_center_lists_scenarios_for_all_eight_courses(self):
        from django.core.management import call_command
        from io import StringIO
        call_command("sync_curriculum", stdout=StringIO())
        page = self.client.get(reverse("practice:center"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "No practice scenarios for this course yet")
        for title in ("Free textbook download with a browser warning", "Ransomware note on the student-society laptop",
                      "Flashlight app with far too many permissions", "A second 'Tanvir' asks for a verification code",
                      "Compromised university email sending spam"):
            self.assertContains(page, title.replace("'", "&#x27;"))

    def _api(self, name, body=None, *args):
        import json
        return self.client.post(reverse(name, args=args), json.dumps(body or {}), content_type="application/json").json()

    def test_full_play_through_with_hint_explanations_and_replay(self):
        from practice.testing import answer_for, convert_all
        from practice.models import Attempt, Scenario
        convert_all()
        start = self.client.post(reverse("practice:start", args=["malware"]), {"scenario_key": "malware_ransomware_note"})
        self.assertRedirects(start, "/practice/malware-ransomware-note/")
        page = self.client.get(start.url)
        self.assertContains(page, "no timer")
        self.assertNotContains(page, "mission-timer")

        began = self._api("practice:api_start", {"scenario": "malware-ransomware-note"})
        evidence = next(s for s in began["content"]["steps"] if s["type"] == "hotspot")
        self.assertIn("USB backup drive (E:)", str(evidence["context"]))            # the old workspace panels
        self.assertIn("Ransomware spreads to anything connected", evidence["tips"]["start"])  # the hint
        steps = Scenario.objects.get(slug="malware-ransomware-note").content["steps"]
        aid = began["attempt_id"]
        for index, step in enumerate(steps):
            if step["type"] in ("story", "mcq"):
                continue
            self._api("practice:api_answer", {"step": index, "answer": answer_for(step)}, aid)
        decide = next(i for i, s in enumerate(steps) if s["type"] == "mcq")
        pay = steps[decide]["options"].index("Pay the Ransom to Get Files Back Today")
        wrong = self._api("practice:api_answer", {"step": decide, "answer": pay}, aid)
        self.assertFalse(wrong["correct"])
        self.assertIn("Files recovered without paying", wrong["text"])            # the best option is explained too
        done = self._api("practice:api_complete", None, aid)
        self.assertEqual(done["xp"], 50)                                            # XP rule unchanged
        self.assertEqual(len(done["debrief"]["learned"]), 3)

        replay = self._api("practice:api_start", {"scenario": "malware-ransomware-note"})
        self.assertNotEqual(replay["attempt_id"], aid)
        self.assertEqual(Attempt.objects.filter(user=self.user).count(), 2)

    def test_every_original_scenario_keeps_its_title_and_decisions(self):
        from practice.models import Scenario
        from practice.testing import convert_all
        convert_all()
        for key, old in SCENARIOS_BY_KEY.items():
            row = Scenario.objects.get(slug=key.replace("_", "-"))
            self.assertEqual(row.title, old["title"])
            decide = next(s for s in row.content["steps"] if s["type"] == "mcq")
            self.assertEqual(decide["options"], [d["label"] for d in old["decisions"].values()])
