"""Every scenario of every topic opens in the interactive engine and never leaks answers."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from practice.graders import ANSWER_KEYS
from practice.models import Scenario
from practice.scenarios import SCENARIOS
from practice.testing import convert_all, play_through

User = get_user_model()


def _keys(value):
    if isinstance(value, dict):
        return set(value).union(*(_keys(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_keys(v) for v in value)) if value else set()
    return set()


class EveryScenarioOpensInTheNewEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        convert_all()
        cls.student = User.objects.create_user(email="student@example.com", password="testpass123", username="student")
        # Staff may preview Coming Soon courses (Course.is_open_to), so every scenario can be started.
        cls.staff = User.objects.create_user(email="staff@example.com", password="testpass123", username="staff", is_staff=True)

    def test_every_original_scenario_was_converted(self):
        slugs = set(Scenario.objects.values_list("slug", flat=True))
        for key in SCENARIOS:
            self.assertIn(key.replace("_", "-"), slugs)

    def test_every_scenario_page_returns_200_and_start_has_no_answer_keys(self):
        scenarios = list(Scenario.objects.select_related("topic"))
        self.assertGreaterEqual(len(scenarios), len(SCENARIOS) + 1)
        for user in (self.student, self.staff):
            self.client.force_login(user)
            for scenario in scenarios:
                page = self.client.get(f"/practice/{scenario.slug}/")
                self.assertEqual(page.status_code, 200, scenario.slug)
                self.assertTemplateUsed(page, "practice/session.html")
        self.client.force_login(self.staff)
        for scenario in scenarios:
            res = self.client.post(reverse("practice:api_start"), json.dumps({"scenario": scenario.slug}),
                                   content_type="application/json")
            self.assertEqual(res.status_code, 201, scenario.slug)
            self.assertFalse(_keys(res.json()) & ANSWER_KEYS, scenario.slug)

    def test_every_scenario_can_be_completed(self):
        self.client.force_login(self.staff)
        for scenario in Scenario.objects.all():
            done = play_through(self.client, scenario.slug, right=True)
            self.assertEqual(done["accuracy"], 100, scenario.slug)

    def test_every_center_card_links_to_the_new_engine(self):
        self.client.force_login(self.student)
        page = self.client.get(reverse("practice:center")).content.decode()
        self.assertNotIn('action="/practice/', page.split('id="pc-catalog"')[0].split("<main")[-1])  # no start forms
        for key, old in SCENARIOS.items():
            if old["domain"] == "osint":   # OSINT stays Coming Soon and has no cards
                continue
            self.assertIn(f'href="/practice/{key.replace("_", "-")}/"', page, key)
        self.assertIn('href="/practice/phish-01-choice/"', page)
        self.assertNotIn("{#", page)          # template comments never leak into the page
