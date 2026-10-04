import pyotp
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import RecoveryCode, UserActivityDay
from games.models import GameAttempt
from pages.models import HomepageVisitDay

User = get_user_model()


class VisitorCounterTests(TestCase):
    def test_refresh_counts_once_per_session(self):
        url = reverse("pages:home")
        self.client.get(url)
        self.client.get(url)
        self.assertEqual(HomepageVisitDay.objects.get().visits, 1)
        self.assertContains(self.client.get(url), "Live homepage visits")
        self.assertContains(self.client.get(url), "not a unique-visitor")

    def test_staff_is_not_counted(self):
        user = User.objects.create_user(email="staff@gmail.com", password="securepass1", is_staff=True)
        self.client.force_login(user)
        self.client.get(reverse("pages:home"))
        self.assertFalse(HomepageVisitDay.objects.exists())


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class TotpTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="recruit@gmail.com", password="securepass1", username="recruit2fa",
            ethical_agreement=True,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_enable_requires_valid_code(self):
        start = self.client.post(reverse("accounts:totp_start"))
        self.assertEqual(start.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)
        bad = self.client.post(reverse("accounts:totp_confirm"), {"code": "000000"})
        self.assertEqual(bad.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)
        secret = self.client.session["pending_totp_secret"]
        code = pyotp.TOTP(secret).now()
        ok = self.client.post(reverse("accounts:totp_confirm"), {"code": code})
        self.assertEqual(ok.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.totp_enabled)
        self.assertEqual(RecoveryCode.objects.filter(user=self.user).count(), 8)
        self.assertNotContains(ok, self.user.totp_secret)

    def test_other_user_cannot_disable(self):
        self.user.totp_enabled = True
        self.user.totp_secret = pyotp.random_base32()
        self.user.save()
        other = User.objects.create_user(email="other2@gmail.com", password="securepass1", username="other2")
        client = Client()
        client.force_login(other)
        client.post(reverse("accounts:totp_disable"), {"password": "securepass1"})
        self.user.refresh_from_db()
        self.assertTrue(self.user.totp_enabled)

    def test_login_requires_totp_and_rejects_bad_code(self):
        secret = pyotp.random_base32()
        self.user.totp_secret = secret
        self.user.totp_enabled = True
        self.user.save()
        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {
            "email": "recruit@gmail.com", "password": "securepass1",
        })
        self.assertRedirects(response, reverse("accounts:verify_totp"))
        self.assertNotIn("_auth_user_id", self.client.session)
        denied = self.client.post(reverse("accounts:verify_totp"), {"code": "000000"})
        self.assertEqual(denied.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        allowed = self.client.post(reverse("accounts:verify_totp"), {"code": pyotp.TOTP(secret).now()})
        self.assertEqual(allowed.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_disabled_totp_keeps_email_challenge(self):
        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {
            "email": "recruit@gmail.com", "password": "securepass1",
        })
        self.assertRedirects(response, reverse("accounts:verify_login"))
        self.assertNotIn("_auth_user_id", self.client.session)


class AnalyticsTests(TestCase):
    def test_staff_only_and_real_counts(self):
        player = User.objects.create_user(email="play@gmail.com", password="securepass1", username="playera")
        staff = User.objects.create_user(
            email="analyst@gmail.com", password="securepass1", username="analyst", is_staff=True,
        )
        player.record_daily_activity()
        GameAttempt.objects.create(
            user=player, game_key="phishing_simulator", score=4, total_questions=5, xp_awarded=80,
        )
        visitor = Client()
        visitor.force_login(player)
        denied = visitor.get(reverse("dashboard:analytics"))
        self.assertEqual(denied.status_code, 403)
        staff_client = Client()
        staff_client.force_login(staff)
        page = staff_client.get(reverse("dashboard:analytics") + "?days=7")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Total registered users")
        self.assertContains(page, "Phishing Simulator")
        self.assertContains(page, "1 attempts")
        self.assertEqual(UserActivityDay.objects.filter(user=player).count(), 1)
        self.assertNotContains(page, "play@gmail.com")
