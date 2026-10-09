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
from .scenarios import DOMAIN_SCENARIO, choose_scenario, get_scenario, scenarios_for_domain
from .views import award_practice_completion, XP_PRACTICE_COMPLETE

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


class PracticeProgressionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="progress@example.com",
            password="testpass123",
            username="progressuser",
        )
        self.client.login(email="progress@example.com", password="testpass123")

    def _session(self):
        return PracticeSession.objects.create(
            user=self.user,
            domain="phishing",
            activity_type="simulation",
            scenario_key=DOMAIN_SCENARIO["phishing"],
            difficulty="beginner",
            score=0,
            max_score=100,
            state={"phase": "investigate", "revealed": []},
        )

    def _finish(self, actions):
        session = self._session()
        for action in actions:
            response = self.client.post(
                reverse("practice:decide", args=[session.pk]),
                {"action": action, "xp": "9999"},
            )
            self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.user.refresh_from_db()
        return session

    def test_first_completion_awards_fixed_xp_not_client_xp(self):
        session = self._finish(["inspect_sender", "inspect_domain", "inspect_link", "report_phishing"])
        self.assertEqual(session.percent, 70)
        self.assertEqual(session.xp_awarded, 50)
        self.assertEqual(self.user.xp, 50)

    def test_each_completed_session_awards_fifty_once(self):
        self._finish(["inspect_sender", "inspect_domain", "inspect_link", "report_phishing"])
        again = self._finish(["inspect_sender", "inspect_domain", "inspect_link", "report_phishing"])
        self.user.refresh_from_db()
        self.assertEqual(again.xp_awarded, 50)
        self.assertEqual(self.user.xp, 100)
        self.assertEqual(
            PracticeSession.objects.filter(user=self.user, domain="phishing", status="completed").count(),
            2,
        )

    def test_worse_score_does_not_lower_dna(self):
        self._finish(["inspect_sender", "inspect_domain", "inspect_link", "report_phishing"])
        worse = self._finish(["ignore"])
        self.user.refresh_from_db()
        self.assertEqual(worse.score, 0)
        self.assertEqual(worse.xp_awarded, 50)
        self.assertEqual(self.user.xp, 100)
        phishing = next(d for d in get_domain_competencies(self.user) if d["slug"] == "phishing")
        self.assertEqual(phishing["practice_percent"], 70)
        self.assertEqual(phishing["percent"], 70)

    def test_zero_and_perfect_scores_both_award_fifty(self):
        zero = self._finish(["ignore"])
        self.assertEqual(zero.score, 0)
        self.assertEqual(zero.xp_awarded, 50)
        perfect = PracticeSession.objects.create(
            user=self.user, domain="phishing", activity_type="simulation",
            scenario_key=DOMAIN_SCENARIO["phishing"], difficulty="beginner",
            score=100, max_score=100, status="completed",
            state={"phase": "completed", "revealed": []},
        )
        gained, _leveled = award_practice_completion(self.user, perfect)
        perfect.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(gained, XP_PRACTICE_COMPLETE)
        self.assertEqual(perfect.xp_awarded, 50)
        self.assertEqual(self.user.xp, 100)
        award_practice_completion(self.user, perfect)
        self.user.refresh_from_db()
        self.assertEqual(self.user.xp, 100)

    def test_completion_twice_does_not_double_xp(self):
        session = self._finish(["ignore"])
        self.client.post(reverse("practice:decide", args=[session.pk]), {"action": "ignore", "xp": "9999"})
        self.client.get(reverse("practice:result", args=[session.pk]))
        self.user.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(session.xp_awarded, 50)
        self.assertEqual(self.user.xp, 50)

    def test_incomplete_session_awards_nothing(self):
        session = self._session()
        self.client.get(reverse("practice:play", args=[session.pk]))
        session.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(session.status, "in_progress")
        self.assertEqual(session.xp_awarded, 0)
        self.assertEqual(self.user.xp, 0)

    def test_higher_score_still_updates_best_practice_percent(self):
        self._finish(["inspect_sender", "inspect_domain", "inspect_link", "report_phishing"])
        better = self._finish([
            "inspect_sender", "inspect_domain", "inspect_link", "view_headers", "check_timeline",
            "report_phishing",
        ])
        self.user.refresh_from_db()
        self.assertEqual(better.percent, 85)
        self.assertEqual(better.xp_awarded, 50)
        self.assertEqual(self.user.xp, 100)
        phishing = next(d for d in get_domain_competencies(self.user) if d["slug"] == "phishing")
        self.assertEqual(phishing["percent"], 85)

    def test_game_and_practice_still_use_the_higher_percent(self):
        PracticeSession.objects.create(
            user=self.user, domain="phishing", activity_type="simulation",
            scenario_key=DOMAIN_SCENARIO["phishing"], difficulty="beginner",
            score=70, max_score=100, status="completed",
            state={"phase": "completed", "revealed": []},
        )
        GameAttempt.objects.create(
            user=self.user, game_key="phishing_simulator", score=9, total_questions=10, xp_awarded=0,
        )
        GameAttempt.objects.create(
            user=self.user, game_key="password_cracker", score=4, total_questions=10, xp_awarded=0,
        )
        PracticeSession.objects.create(
            user=self.user, domain="password", activity_type="simulation",
            scenario_key=DOMAIN_SCENARIO["password"], difficulty="beginner",
            score=90, max_score=100, status="completed",
            state={"phase": "completed", "revealed": []},
        )
        rows = {row["slug"]: row for row in get_domain_competencies(self.user)}
        self.assertEqual(rows["phishing"]["percent"], 90)
        self.assertEqual(rows["password"]["percent"], 90)

    def test_practice_xp_can_level_up_and_award_rising_star_once(self):
        from achievements.models import UserBadge
        self.user.xp = 190
        self.user.level = 2
        self.user.save(update_fields=["xp", "level"])
        self._finish(["inspect_sender", "inspect_domain", "inspect_link", "report_phishing"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.xp, 240)
        self.assertEqual(self.user.level, 3)
        badges = UserBadge.objects.filter(user=self.user, badge__code="level_up")
        self.assertEqual(badges.count(), 1)
        self._finish([
            "inspect_sender", "inspect_domain", "inspect_link", "view_headers", "check_timeline",
            "report_phishing",
        ])
        self.assertEqual(UserBadge.objects.filter(user=self.user, badge__code="level_up").count(), 1)

    def test_other_user_cannot_finish_session(self):
        session = self._session()
        self.client.logout()
        self.client.login(email="progress@example.com", password="testpass123")
        other = User.objects.create_user(email="outsider@example.com", password="testpass123", username="outsider")
        self.client.force_login(other)
        response = self.client.post(reverse("practice:decide", args=[session.pk]), {"action": "ignore", "xp": "100"})
        self.assertEqual(response.status_code, 404)
        self.user.refresh_from_db()
        self.assertEqual(self.user.xp, 0)

    def test_result_page_shows_competency_only_when_it_improves(self):
        self.client.login(email="progress@example.com", password="testpass123")
        first = PracticeSession.objects.create(
            user=self.user, domain="network", activity_type="simulation",
            scenario_key=DOMAIN_SCENARIO["network"], difficulty="beginner",
            score=85, max_score=100, status="completed", xp_awarded=34,
            strengths="Collected the required evidence.",
            improvements="Review the containment choice.",
            state={"phase": "completed", "revealed": [], "consequence": {"title": "Contained", "body": "Done", "quality": "correct", "decision_label": "Isolate", "response": "Host isolated"}},
        )
        page = self.client.get(reverse("practice:result", args=[first.pk]))
        self.assertContains(page, "0% → 85%")
        self.assertContains(page, "+85 competency points")
        self.assertContains(page, "+34 XP")
        self.assertContains(page, "weakest competency")
        later = PracticeSession.objects.create(
            user=self.user, domain="network", activity_type="simulation",
            scenario_key=DOMAIN_SCENARIO["network"], difficulty="beginner",
            score=40, max_score=100, status="completed", xp_awarded=0,
            strengths="Collected the required evidence.",
            improvements="Review the containment choice.",
            state={"phase": "completed", "revealed": [], "consequence": {"title": "Contained", "body": "Done", "quality": "poor", "decision_label": "Wait", "response": "Delayed"}},
        )
        page = self.client.get(reverse("practice:result", args=[later.pk]))
        self.assertContains(page, "unchanged")
        self.assertNotContains(page, "competency points")
        self.assertContains(page, "+0 XP")
        self.assertContains(page, "Collected the required evidence.")


class PracticeScenarioPoolTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="pool@example.com", password="testpass123", username="pooluser",
        )
        self.client.login(email="pool@example.com", password="testpass123")

    def test_each_domain_has_four_distinct_scenarios(self):
        for slug in ("phishing", "password", "network", "cryptography", "osint"):
            rows = scenarios_for_domain(slug)
            self.assertGreaterEqual(len(rows), 4)
            titles = [row["title"] for row in rows]
            self.assertEqual(len(titles), len(set(titles)))
            modes = {row["activity_type"] for row in rows}
            self.assertIn("simulation", modes)
            self.assertIn("incident", modes)
            for row in rows:
                self.assertIn(row["difficulty"], ("beginner", "intermediate", "advanced"))
                self.assertTrue(row["investigations"])
                self.assertTrue(row["decisions"])
                self.assertTrue(row["objective"])
                self.assertTrue(row["scene"]["nodes"])

    def test_activity_filter_selects_different_scenarios(self):
        simulation = choose_scenario("network", [], "simulation")
        incident = choose_scenario("network", [], "incident")
        self.assertNotEqual(simulation["key"], incident["key"])
        self.assertEqual(simulation["activity_type"], "simulation")
        self.assertEqual(incident["activity_type"], "incident")

    def test_recent_scenario_is_not_repeated_while_others_remain(self):
        first = choose_scenario("cryptography", [], None)
        second = choose_scenario("cryptography", [first["key"]], None)
        self.assertNotEqual(first["key"], second["key"])
        keys = [row["key"] for row in scenarios_for_domain("cryptography")]
        recent = list(reversed(keys))
        cycled = choose_scenario("cryptography", recent, None)
        self.assertNotEqual(cycled["key"], recent[0])
        self.assertIn(cycled["key"], keys)

    def test_start_rotates_after_completion(self):
        first = self.client.post(reverse("practice:start", args=["osint"]), {})
        self.assertEqual(first.status_code, 302)
        session = PracticeSession.objects.get(user=self.user)
        session.status = "completed"
        session.completed_at = session.created_at
        session.save(update_fields=["status", "completed_at"])
        self.client.post(reverse("practice:start", args=["osint"]), {})
        keys = list(
            PracticeSession.objects.filter(user=self.user).order_by("pk").values_list("scenario_key", flat=True)
        )
        self.assertEqual(len(keys), 2)
        self.assertNotEqual(keys[0], keys[1])

    def test_center_shows_scenario_counts_and_history_shows_titles(self):
        page = self.client.get(reverse("practice:center"))
        self.assertContains(page, "4 scenarios available")
        PracticeSession.objects.create(
            user=self.user, domain="network", activity_type="incident",
            scenario_key="network_dns_beacon", difficulty="intermediate",
            score=85, max_score=100, status="completed",
            state={"phase": "completed"},
        )
        history = self.client.get(reverse("practice:history"))
        self.assertContains(history, "Network Defense")
        self.assertContains(history, "DNS beacon investigation")

    def test_center_lets_user_start_any_scenario(self):
        page = self.client.get(reverse("practice:center"))
        self.assertContains(page, "Unusual outbound traffic from internal host")
        self.assertContains(page, "Port scan response")
        self.assertContains(page, "DNS beacon investigation")
        self.assertContains(page, "Lateral movement")
        self.assertContains(page, "START THIS SCENARIO")
        started = self.client.post(
            reverse("practice:start", args=["network"]),
            {"scenario_key": "network_dns_beacon"},
        )
        self.assertEqual(started.status_code, 302)
        session = PracticeSession.objects.get(user=self.user, domain="network")
        self.assertEqual(session.scenario_key, "network_dns_beacon")
        rejected = self.client.post(
            reverse("practice:start", args=["phishing"]),
            {"scenario_key": "network_dns_beacon", "xp": "50", "score": "100"},
        )
        self.assertEqual(rejected.status_code, 302)
        self.assertFalse(PracticeSession.objects.filter(user=self.user, domain="phishing").exists())
        session.status = "completed"
        session.score = 85
        session.xp_awarded = 0
        session.save(update_fields=["status", "score", "xp_awarded"])
        again = self.client.get(reverse("practice:center"))
        self.assertContains(again, "COMPLETED")
        self.assertContains(again, "BEST 85%")

