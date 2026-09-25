from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from games.models import GameAttempt
from games.registry import GAMES_REGISTRY
from certificates.eligibility import is_eligible_for_certificate
from certificates.competency import get_competency_profile, competency_band

from .models import PracticeSession
from .engine import apply_action, open_workspace
from .adaptive import get_cyber_dna, get_recommendation, get_domain_competencies
from .scenarios import DOMAIN_SCENARIO, get_scenario

User = get_user_model()


class PracticeSystemTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="practice@example.com",
            password="testpass123",
            username="practiceuser",
        )
        self.other = User.objects.create_user(
            email="other@example.com",
            password="testpass123",
            username="otheruser",
        )

    def _start_session(self, activity="simulation"):
        self.client.login(email="practice@example.com", password="testpass123")
        res = self.client.post(
            reverse("practice:start", args=["phishing"]),
            {"activity_type": activity, "difficulty": "beginner"},
        )
        self.assertEqual(res.status_code, 302)
        return PracticeSession.objects.get(user=self.user)

    def test_practice_center_requires_login(self):
        res = self.client.get(reverse("practice:center"))
        self.assertEqual(res.status_code, 302)
        self.assertIn("/accounts/login/", res.url)

    def test_logged_in_user_can_open_practice_center(self):
        self.client.login(email="practice@example.com", password="testpass123")
        res = self.client.get(reverse("practice:center"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "PHISHING")
        self.assertContains(res, "PASSWORD SECURITY")

    def test_start_simulation_opens_briefing_then_console(self):
        session = self._start_session()
        self.assertEqual(session.activity_type, "simulation")
        self.assertEqual(session.state.get("phase"), "briefing")

        res = self.client.get(reverse("practice:play", args=[session.pk]))
        self.assertContains(res, "EMAIL SECURITY CONSOLE")
        self.assertContains(res, "CQ-PH-001")
        self.assertContains(res, "OPEN EMAIL CONSOLE")

        res = self.client.post(reverse("practice:open", args=[session.pk]))
        self.assertEqual(res.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.state.get("phase"), "investigate")

        res = self.client.get(reverse("practice:play", args=[session.pk]))
        self.assertContains(res, "INVESTIGATION TOOLS")
        self.assertContains(res, "EVIDENCE LOCKER")
        self.assertContains(res, "Inspect Sender")
        # Evidence values must NOT appear before investigation
        self.assertNotContains(res, "micros0ft-help.example")

    def test_progressive_evidence_and_valid_decision(self):
        session = self._start_session()
        open_workspace(session)
        session.refresh_from_db()

        res = self.client.post(
            reverse("practice:decide", args=[session.pk]),
            {"action": "inspect_sender"},
        )
        self.assertEqual(res.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(len(session.decisions), 1)
        self.assertIn("inspect_sender", session.state["revealed"])

        res = self.client.get(reverse("practice:play", args=[session.pk]))
        self.assertContains(res, "micros0ft-help.example")

    def test_invalid_decision_rejected(self):
        session = self._start_session()
        open_workspace(session)
        res = self.client.post(
            reverse("practice:decide", args=[session.pk]),
            {"action": "not_a_real_action"},
        )
        self.assertEqual(res.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.decisions, [])

    def test_consequence_and_score_saved(self):
        session = PracticeSession.objects.create(
            user=self.user,
            domain="phishing",
            activity_type="incident",
            scenario_key=DOMAIN_SCENARIO["phishing"],
            difficulty="beginner",
            score=0,
            max_score=100,
            state={"phase": "investigate", "revealed": []},
        )
        for action in ("inspect_sender", "inspect_domain", "inspect_link"):
            apply_action(session, action)
            session.refresh_from_db()
        before = session.score
        result = apply_action(session, "report_phishing")
        session.refresh_from_db()
        self.assertTrue(result["ended"])
        self.assertEqual(session.status, "completed")
        self.assertGreater(session.score, before)
        self.assertIn("contained", result["consequence"]["title"].lower())
        self.assertTrue(session.result_summary)

    def test_early_report_penalty(self):
        session = PracticeSession.objects.create(
            user=self.user,
            domain="phishing",
            activity_type="simulation",
            scenario_key=DOMAIN_SCENARIO["phishing"],
            difficulty="beginner",
            score=0,
            max_score=100,
            state={"phase": "investigate", "revealed": []},
        )
        result = apply_action(session, "report_phishing")
        session.refresh_from_db()
        self.assertTrue(result["ended"])
        self.assertEqual(result["consequence"]["missing_penalty"], -10)
        # correct decision 40 + missing -10 = 30
        self.assertEqual(session.score, 30)

    def test_unsafe_open_link_consequence(self):
        session = PracticeSession.objects.create(
            user=self.user,
            domain="phishing",
            activity_type="simulation",
            scenario_key=DOMAIN_SCENARIO["phishing"],
            difficulty="beginner",
            score=0,
            max_score=100,
            state={"phase": "investigate", "revealed": ["inspect_sender", "inspect_domain", "inspect_link"]},
        )
        result = apply_action(session, "open_link")
        self.assertEqual(result["consequence"]["quality"], "unsafe")
        self.assertIn("compromised", result["consequence"]["body"].lower())

    def test_all_five_domain_consoles_exist(self):
        for slug in ("phishing", "password", "network", "cryptography", "osint"):
            scenario = get_scenario(DOMAIN_SCENARIO[slug])
            self.assertTrue(scenario["environment"])
            self.assertTrue(scenario["investigations"])
            self.assertTrue(scenario["decisions"])
            self.assertTrue(scenario["workspace"])

    def test_cyber_dna_and_weakest_recommendation(self):
        GameAttempt.objects.create(
            user=self.user, game_key="network_defense",
            score=9, total_questions=10, xp_awarded=0,
        )
        GameAttempt.objects.create(
            user=self.user, game_key="password_cracker",
            score=8, total_questions=10, xp_awarded=0,
        )
        dna = get_cyber_dna(self.user)
        self.assertEqual(dna["weakest"]["slug"], "phishing")
        rec = get_recommendation(self.user)
        self.assertEqual(rec["domain_slug"], "phishing")
        self.assertIn("weakest", rec["reason"].lower())

    def test_user_cannot_access_other_history_session(self):
        session = PracticeSession.objects.create(
            user=self.other,
            domain="phishing",
            activity_type="simulation",
            scenario_key=DOMAIN_SCENARIO["phishing"],
            difficulty="beginner",
            score=80,
            max_score=100,
            status="completed",
            state={"phase": "completed", "revealed": []},
        )
        self.client.login(email="practice@example.com", password="testpass123")
        res = self.client.get(reverse("practice:result", args=[session.pk]))
        self.assertEqual(res.status_code, 404)

    def test_existing_games_registry_intact(self):
        keys = {g["key"] for g in GAMES_REGISTRY}
        for key in ("phishing_simulator", "password_cracker", "network_defense", "cryptography", "osint"):
            self.assertIn(key, keys)

    def test_certificate_competency_still_works(self):
        profile = get_competency_profile(self.user)
        self.assertEqual(len(profile["categories"]), 5)
        self.assertEqual(competency_band(92), "EXPERT")
        self.user.is_staff = True
        self.user.save()
        self.assertTrue(is_eligible_for_certificate(self.user))

    def test_domain_competencies_dynamic(self):
        rows = get_domain_competencies(self.user)
        self.assertEqual(len(rows), 5)
