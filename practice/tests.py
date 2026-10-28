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
from .testing import convert_all, play_through

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

    def test_practice_center_requires_login(self):
        res = self.client.get(reverse("practice:center"))
        self.assertEqual(res.status_code, 302)
        self.assertIn("/accounts/login/", res.url)

    def test_logged_in_user_can_open_practice_center(self):
        self.client.login(email="practice@example.com", password="testpass123")
        res = self.client.get(reverse("practice:center"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Phishing")
        self.assertContains(res, "Password Security")

    def test_start_opens_the_scenario_in_the_interactive_engine(self):
        convert_all()
        self.client.login(email="practice@example.com", password="testpass123")
        res = self.client.post(reverse("practice:start", args=["phishing"]), {"activity_type": "simulation"})
        self.assertEqual(res.status_code, 302)
        self.assertRegex(res.url, r"^/practice/phishing-[a-z-]+/$")
        page = self.client.get(res.url)
        self.assertTemplateUsed(page, "practice/session.html")
        self.assertFalse(PracticeSession.objects.filter(user=self.user).exists())  # nothing recorded until finished

    def test_old_console_urls_send_unfinished_sessions_to_the_new_engine(self):
        convert_all()
        self.client.login(email="practice@example.com", password="testpass123")
        session = PracticeSession.objects.create(
            user=self.user, domain="phishing", activity_type="simulation",
            scenario_key="phishing_bec_payment", difficulty="advanced",
            state={"phase": "investigate", "revealed": []},
        )
        target = reverse("practice:session", args=["phishing-bec-payment"])
        self.assertRedirects(self.client.get(reverse("practice:play", args=[session.pk])), target)
        self.assertRedirects(self.client.post(reverse("practice:open", args=[session.pk])), target)
        self.assertRedirects(self.client.post(reverse("practice:decide", args=[session.pk]), {"action": "send_wire"}), target)
        self.assertRedirects(self.client.get(reverse("practice:result", args=[session.pk])), target)
        self.assertRedirects(self.client.get("/practice/phishing/"), reverse("practice:center") + "?topic=phishing",
                             fetch_redirect_response=False)

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
        # Retired missions stay listed so past attempts keep their names.
        for key in ("phishing_simulator", "password_cracker", "network_defense", "cryptography", "osint"):
            self.assertIn(key, keys)

    def test_certificate_competency_still_works(self):
        profile = get_competency_profile(self.user)
        self.assertEqual(len(profile["categories"]), 8)
        self.assertEqual(competency_band(92), "EXPERT")
        self.user.is_staff = True
        self.user.save()
        self.assertTrue(is_eligible_for_certificate(self.user))

    def test_domain_competencies_dynamic(self):
        rows = get_domain_competencies(self.user)
        # Domains list includes steganography; OSINT is coming_soon but still returned
        from practice.scenarios import DOMAINS
        self.assertEqual(len(rows), len(DOMAINS))


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

    def test_completion_awards_the_fixed_fifty_xp_and_records_the_session(self):
        convert_all()
        done = play_through(self.client, "phishing-microsoft-disable", right=True)
        self.user.refresh_from_db()
        self.assertEqual((done["xp"], done["accuracy"], self.user.xp), (50, 100, 50))
        record = PracticeSession.objects.get(user=self.user)
        self.assertEqual((record.domain, record.scenario_key, record.status, record.score, record.xp_awarded),
                         ("phishing", "phishing_microsoft_disable", "completed", 100, 0))  # XP lives on the attempt

    def test_each_completed_attempt_awards_fifty_and_worse_score_does_not_lower_dna(self):
        convert_all()
        play_through(self.client, "phishing-microsoft-disable", right=True)
        worse = play_through(self.client, "phishing-microsoft-disable", right=False)
        self.user.refresh_from_db()
        self.assertEqual((worse["accuracy"], worse["xp"], self.user.xp), (0, 50, 100))
        phishing = next(d for d in get_domain_competencies(self.user) if d["slug"] == "phishing")
        self.assertEqual(phishing["practice_percent"], 100)

    def test_unfinished_attempt_awards_nothing_and_cannot_be_finished_by_someone_else(self):
        import json
        convert_all()
        start = self.client.post(reverse("practice:api_start"), json.dumps({"scenario": "phishing-bec-payment"}),
                                 content_type="application/json").json()
        self.assertEqual(self.client.post(reverse("practice:api_complete", args=[start["attempt_id"]])).status_code, 400)
        other = User.objects.create_user(email="outsider@example.com", password="testpass123", username="outsider")
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse("practice:api_complete", args=[start["attempt_id"]])).status_code, 404)
        self.user.refresh_from_db()
        self.assertEqual(self.user.xp, 0)
        self.assertFalse(PracticeSession.objects.filter(user=self.user).exists())

    def test_practice_xp_can_level_up_and_award_rising_star_once(self):
        from achievements.models import UserBadge
        convert_all()
        self.user.xp = 190
        self.user.level = 2
        self.user.save(update_fields=["xp", "level"])
        play_through(self.client, "phishing-microsoft-disable")
        self.user.refresh_from_db()
        self.assertEqual((self.user.xp, self.user.level), (240, 3))
        self.assertEqual(UserBadge.objects.filter(user=self.user, badge__code="level_up").count(), 1)
        play_through(self.client, "phishing-google-login")
        self.assertEqual(UserBadge.objects.filter(user=self.user, badge__code="level_up").count(), 1)

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
        convert_all()
        first = self.client.post(reverse("practice:start", args=["network"]), {})
        self.assertEqual(first.status_code, 302)
        PracticeSession.objects.create(
            user=self.user, domain="network", activity_type="simulation",
            scenario_key=first.url.strip("/").split("/")[-1].replace("-", "_"), difficulty="beginner",
            score=80, status="completed", state={"engine": "interactive"},
        )
        second = self.client.post(reverse("practice:start", args=["network"]), {})
        self.assertNotEqual(first.url, second.url)

    def test_center_shows_scenario_counts_and_history_shows_titles(self):
        page = self.client.get(reverse("practice:center"))
        self.assertContains(page, "Scenarios")
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
        convert_all()
        page = self.client.get(reverse("practice:center"))
        for title in ("Unusual outbound traffic from internal host", "Port scan response",
                      "DNS beacon investigation", "Lateral movement"):
            self.assertContains(page, title)
        self.assertContains(page, "Start scenario")
        self.assertContains(page, 'href="/practice/network-dns-beacon/"')
        started = self.client.post(reverse("practice:start", args=["network"]), {"scenario_key": "network_dns_beacon"})
        self.assertRedirects(started, "/practice/network-dns-beacon/")
        rejected = self.client.post(
            reverse("practice:start", args=["phishing"]),
            {"scenario_key": "network_dns_beacon", "xp": "50", "score": "100"},
        )
        self.assertRedirects(rejected, reverse("practice:center"))
        PracticeSession.objects.create(
            user=self.user, domain="network", activity_type="incident", scenario_key="network_dns_beacon",
            difficulty="intermediate", score=85, status="completed", state={"engine": "interactive"},
        )
        again = self.client.get(reverse("practice:center"))
        self.assertContains(again, "COMPLETED")
        self.assertContains(again, "BEST 85%")

