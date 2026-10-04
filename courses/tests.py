from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from courses.models import Course

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
        self.assertContains(response, "vendor/page-flip/page-flip.browser.js")
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
