from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from notifications.models import Notification

User = get_user_model()


class NotificationRedirectTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="notify@gmail.com",
            password="securepass1",
            username="notifyuser",
            ethical_agreement=True,
        )
        self.client.force_login(self.user)

    def test_internal_path_redirects(self):
        note = Notification.objects.create(
            user=self.user, message="Go dashboard", link_url="/dashboard/"
        )
        response = self.client.get(reverse("notifications:redirect", args=[note.pk]))
        self.assertRedirects(response, "/dashboard/", fetch_redirect_response=False)

    def test_external_url_is_not_an_open_redirect(self):
        note = Notification.objects.create(
            user=self.user,
            message="Evil",
            link_url="https://malicious-site.example/phish",
        )
        response = self.client.get(reverse("notifications:redirect", args=[note.pk]))
        self.assertRedirects(
            response, reverse("dashboard:home"), fetch_redirect_response=False
        )
        note.refresh_from_db()
        self.assertEqual(note.link_url, "https://malicious-site.example/phish")
