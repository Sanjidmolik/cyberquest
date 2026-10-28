import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from courses.models import Course, CourseProgress
from courses.progress import server_total_pages

User = get_user_model()


class LearningBookTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="reader@gmail.com", password="securepass1", username="reader",
            ethical_agreement=True,
        )
        self.client.force_login(self.user)
        self.course = Course.objects.create(
            code="PHISH",
            title="Phishing",
            short_description="How to spot a fake message.",
            content="A suspicious link is not the bank.\n\nReport it instead of clicking.",
            is_published=True,
        )

    def test_reader_uses_pageflip_and_existing_content(self):
        response = self.client.get(reverse("courses:detail", args=[self.course.code]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A suspicious link is not the bank.")
        self.assertContains(response, "courses/js/vendor/page-flip.browser.js")
        self.assertContains(response, reverse("games:phishing_simulator"))
        self.assertContains(response, reverse("pages:home"))

    def test_learning_route_opens_the_same_course(self):
        response = self.client.get("/learning/phishing/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "How to spot a fake message.")

    def test_missing_topic_does_not_invent_content(self):
        response = self.client.get("/learning/cryptography/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Unable to load this learning module.", status_code=404)

    def test_mark_complete_rejects_forged_client_page_totals(self):
        url = reverse("courses:mark_complete", args=[self.course.code])
        forged = self.client.post(
            url,
            data=json.dumps({"pages_reached": 999, "total_pages": 1}),
            content_type="application/json",
        )
        self.assertEqual(forged.status_code, 400)
        self.assertFalse(
            CourseProgress.objects.filter(user=self.user, course=self.course).exists()
        )

    def test_mark_complete_accepts_server_backed_progress(self):
        total = server_total_pages(self.course)
        progress_url = reverse("courses:save_progress", args=[self.course.code])
        reached = 0
        while reached < total - 1:
            reached = min(reached + 2, total - 1)
            self.client.post(
                progress_url,
                data=json.dumps({"page_index": reached}),
                content_type="application/json",
            )

        ok = self.client.post(
            reverse("courses:mark_complete", args=[self.course.code]),
            data=json.dumps({"pages_reached": total - 1, "total_pages": 1}),
            content_type="application/json",
        )
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(
            CourseProgress.objects.filter(user=self.user, course=self.course).exists()
        )


class MissionUnlockTests(TestCase):
    """Each mission unlocks once its own course is completed; admins can play everything."""

    def setUp(self):
        self.student = User.objects.create_user(
            email="unlock@gmail.com", password="securepass1", username="unlock", ethical_agreement=True,
        )
        self.phishing = Course.objects.create(code="MOD-01", title="Phishing attack", short_description="x",
                                              content="Spot fakes.", is_published=True)
        self.password = Course.objects.create(code="MOD-02", title="Password Cracker", short_description="x",
                                              content="Use passphrases.", is_published=True)

    def test_finishing_a_course_unlocks_only_its_mission(self):
        from courses.progress import is_game_unlocked

        self.assertFalse(is_game_unlocked(self.student, "phishing_simulator"))
        CourseProgress.objects.create(user=self.student, course=self.phishing)
        self.assertTrue(is_game_unlocked(self.student, "phishing_simulator"))
        self.assertFalse(is_game_unlocked(self.student, "password_cracker"))
        self.assertFalse(is_game_unlocked(self.student, "cryptography"))  # no course yet

    def test_locked_mission_redirects_to_learn_and_open_one_loads(self):
        self.client.force_login(self.student)
        CourseProgress.objects.create(user=self.student, course=self.phishing)
        locked = self.client.get(reverse("games:password_cracker"))
        self.assertRedirects(locked, reverse("courses:intro"), fetch_redirect_response=False)
        opened = self.client.get(reverse("games:phishing_simulator"))
        self.assertNotEqual(opened.get("Location"), reverse("courses:intro"))

    def test_admins_can_play_every_mission(self):
        from courses.progress import is_game_unlocked

        admin = User.objects.create_user(email="boss@gmail.com", password="securepass1", username="boss",
                                         is_staff=True, is_superuser=True)
        for key in ("phishing_simulator", "password_cracker", "network_defense", "cryptography", "steganography"):
            self.assertTrue(is_game_unlocked(admin, key))

    def test_dashboard_cards_lock_per_mission(self):
        from dashboard.utils import get_dashboard_context

        CourseProgress.objects.create(user=self.student, course=self.phishing)
        cards = {m["key"]: m for m in get_dashboard_context(self.student)["active_missions"]}
        self.assertFalse(cards["phishing_simulator"]["locked"])
        self.assertTrue(cards["password_cracker"]["locked"])
        self.assertNotIn("osint", cards)  # coming soon: its own row, not an active mission
