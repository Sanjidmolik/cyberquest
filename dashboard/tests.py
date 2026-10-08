from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from games.models import QuestionSet
from notifications.models import Notification
from pages.models import ContactMessage
from question_bank.models import QuestionBank

User = get_user_model()


class AdminCommandCenterAccessTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(email="student@example.com", password="pass12345")
        self.staff = User.objects.create_user(
            email="staff@example.com", password="pass12345", is_staff=True
        )
        self.superuser = User.objects.create_superuser(email="root@example.com", password="pass12345")

    def test_anonymous_is_redirected(self):
        response = self.client.get(reverse("ops:overview"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_student_and_staff_are_forbidden(self):
        for user in (self.student, self.staff):
            self.client.force_login(user)
            response = self.client.get(reverse("ops:overview"))
            self.assertEqual(response.status_code, 403)

    def test_superuser_can_open_command_pages(self):
        self.client.force_login(self.superuser)
        names = [
            "overview", "students", "courses", "games", "practice",
            "questions", "review", "certificates", "achievements",
            "notifications", "contact", "analytics", "settings", "search", "leaderboard",
        ]
        for name in names:
            response = self.client.get(reverse(f"ops:{name}"))
            self.assertEqual(response.status_code, 200, name)
        html = self.client.get(reverse("ops:overview")).content.decode()
        self.assertNotIn("SECRET_KEY", html)
        self.assertNotIn("password", html.lower())

    def test_contact_resolve_and_unsafe_notification(self):
        self.client.force_login(self.superuser)
        message = ContactMessage.objects.create(name="Ada", email="ada@example.com", message="Hello")
        response = self.client.post(reverse("ops:resolve_contact", args=[message.pk]), {"resolved": "1"})
        self.assertEqual(response.status_code, 302)
        message.refresh_from_db()
        self.assertTrue(message.is_resolved)

        response = self.client.post(reverse("ops:notifications"), {
            "email": self.student.email,
            "message": "Review your progress",
            "link_url": "https://evil.example/phish",
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Notification.objects.filter(user=self.student).exists())

        response = self.client.post(reverse("ops:notifications"), {
            "email": self.student.email,
            "message": "Review your progress",
            "link_url": "/dashboard/",
        })
        self.assertEqual(response.status_code, 302)
        note = Notification.objects.get(user=self.student)
        self.assertEqual(note.link_url, "/dashboard/")

    def test_approve_only_review_banks(self):
        self.client.force_login(self.superuser)
        bank = QuestionBank.objects.create(
            title="Phish bank",
            domain="phishing_simulator",
            source_content="Source text long enough.",
            status=QuestionBank.STATUS_REVIEW,
        )
        qset = QuestionSet.objects.create(
            course="phishing_simulator",
            set_number=1,
            set_type=QuestionSet.SET_TYPE_NORMAL,
            question_bank=bank,
            status=QuestionSet.STATUS_REVIEW,
        )
        response = self.client.post(reverse("ops:approve_bank", args=[bank.pk]))
        self.assertEqual(response.status_code, 302)
        bank.refresh_from_db()
        qset.refresh_from_db()
        self.assertEqual(bank.status, QuestionBank.STATUS_APPROVED)
        self.assertEqual(qset.status, QuestionSet.STATUS_APPROVED)

        draft = QuestionBank.objects.create(
            title="Draft bank",
            domain="phishing_simulator",
            source_content="Another source.",
            status=QuestionBank.STATUS_DRAFT,
        )
        self.client.post(reverse("ops:approve_bank", args=[draft.pk]))
        draft.refresh_from_db()
        self.assertEqual(draft.status, QuestionBank.STATUS_DRAFT)
