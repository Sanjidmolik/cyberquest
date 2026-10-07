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
