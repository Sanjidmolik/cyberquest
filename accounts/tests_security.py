"""TOTP encryption, replay protection, hashed codes, and admin second-factor tests."""

from datetime import timedelta
from importlib import import_module

import pyotp
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.codes import check_code, generate_code
from accounts.crypto import decrypt_secret, encrypt_secret, is_encrypted, rotate_secret
from accounts.models import VerificationCode
from accounts.totp import USER_FAILURE_LIMIT, verify_user_totp

UserModel = get_user_model()
KEY_A = Fernet.generate_key().decode()
KEY_B = Fernet.generate_key().decode()


def _user(email="secure@gmail.com", **extra):
    return UserModel.objects.create_user(
        email=email, password="securepass1!", username=email.split("@")[0],
        ethical_agreement=True, **extra,
    )


def _enable_totp(user):
    secret = pyotp.random_base32()
    user.set_totp_secret(secret)
    user.totp_enabled = True
    user.save()
    return secret


@override_settings(FIELD_ENCRYPTION_KEYS=[KEY_A])
class TotpSecretEncryptionTests(TestCase):
    def test_secret_is_stored_encrypted_and_reads_back(self):
        user = _user()
        secret = _enable_totp(user)
        stored = UserModel.objects.values_list("totp_secret", flat=True).get(pk=user.pk)
        self.assertTrue(is_encrypted(stored))
        self.assertNotIn(secret, stored)
        user.refresh_from_db()
        self.assertEqual(user.get_totp_secret(), secret)

    def test_secret_written_before_a_dedicated_key_stays_readable(self):
        with self.settings(FIELD_ENCRYPTION_KEYS=[]):
            early = encrypt_secret("JBSWY3DPEHPK3PXP")
        self.assertEqual(decrypt_secret(early), "JBSWY3DPEHPK3PXP")
        self.assertTrue(decrypt_secret(rotate_secret(early)) == "JBSWY3DPEHPK3PXP")

    def test_secret_survives_secret_key_rotation_via_fallbacks(self):
        with self.settings(FIELD_ENCRYPTION_KEYS=[], SECRET_KEY="old-secret-key-for-test-only-0123456789"):
            early = encrypt_secret("JBSWY3DPEHPK3PXP")
        with self.settings(FIELD_ENCRYPTION_KEYS=[], SECRET_KEY="new-secret-key-for-test-only-9876543210",
                           SECRET_KEY_FALLBACKS=["old-secret-key-for-test-only-0123456789"]):
            self.assertEqual(decrypt_secret(early), "JBSWY3DPEHPK3PXP")

    def test_legacy_plaintext_secret_is_still_readable(self):
        self.assertEqual(decrypt_secret("JBSWY3DPEHPK3PXP"), "JBSWY3DPEHPK3PXP")

    def test_rotation_keeps_old_ciphertext_readable(self):
        old = encrypt_secret("JBSWY3DPEHPK3PXP")
        with self.settings(FIELD_ENCRYPTION_KEYS=[KEY_B, KEY_A]):
            self.assertEqual(decrypt_secret(old), "JBSWY3DPEHPK3PXP")
            rotated = rotate_secret(old)
        with self.settings(FIELD_ENCRYPTION_KEYS=[KEY_B]):
            self.assertEqual(decrypt_secret(rotated), "JBSWY3DPEHPK3PXP")

    def test_data_migration_encrypts_legacy_plaintext_once(self):
        user = _user()
        UserModel.objects.filter(pk=user.pk).update(totp_secret="JBSWY3DPEHPK3PXP", totp_enabled=True)
        migration = import_module("accounts.migrations.0013_protect_stored_secrets")
        migration.encrypt_totp_secrets(UserModel)
        first = UserModel.objects.values_list("totp_secret", flat=True).get(pk=user.pk)
        migration.encrypt_totp_secrets(UserModel)  # idempotent: no double encryption
        self.assertEqual(UserModel.objects.values_list("totp_secret", flat=True).get(pk=user.pk), first)
        user.refresh_from_db()
        self.assertTrue(is_encrypted(user.totp_secret))
        self.assertEqual(user.get_totp_secret(), "JBSWY3DPEHPK3PXP")

    def test_enrollment_secret_in_session_is_encrypted(self):
        user = _user()
        self.client.force_login(user)
        self.client.post(reverse("accounts:totp_start"))
        stored = self.client.session["pending_totp_secret"]
        self.assertTrue(is_encrypted(stored))


@override_settings(FIELD_ENCRYPTION_KEYS=[KEY_A])
class TotpReplayTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _user()
        self.secret = _enable_totp(self.user)

    def test_code_cannot_be_used_twice(self):
        code = pyotp.TOTP(self.secret).now()
        self.assertTrue(verify_user_totp(self.user, code))
        self.assertFalse(verify_user_totp(self.user, code))
        fresh = UserModel.objects.get(pk=self.user.pk)
        self.assertFalse(verify_user_totp(fresh, code))

    def test_older_step_is_rejected_after_newer_step(self):
        totp = pyotp.TOTP(self.secret)
        now = timezone.now()
        self.assertTrue(verify_user_totp(self.user, totp.at(now)))
        previous = totp.at(now - timedelta(seconds=30))
        self.assertFalse(verify_user_totp(self.user, previous))

    def _start_login(self, client):
        response = client.post(reverse("accounts:login"), {
            "email": self.user.email, "password": "securepass1!",
        })
        self.assertRedirects(response, reverse("accounts:verify_totp"))

    def test_replayed_code_does_not_sign_in_second_client(self):
        code = pyotp.TOTP(self.secret).now()
        first, second = Client(), Client()
        self._start_login(first)
        self._start_login(second)
        first.post(reverse("accounts:verify_totp"), {"code": code})
        self.assertIn("_auth_user_id", first.session)
        second.post(reverse("accounts:verify_totp"), {"code": code})
        self.assertNotIn("_auth_user_id", second.session)

    def test_account_lock_survives_new_sessions(self):
        for _ in range(USER_FAILURE_LIMIT):
            client = Client()
            self._start_login(client)
            client.post(reverse("accounts:verify_totp"), {"code": "000000"})
        client = Client()
        self._start_login(client)
        locked = client.post(reverse("accounts:verify_totp"), {"code": pyotp.TOTP(self.secret).now()})
        self.assertContains(locked, "Too many attempts")
        self.assertNotIn("_auth_user_id", client.session)


@override_settings(FIELD_ENCRYPTION_KEYS=[KEY_A])
class SessionInvalidationTests(TestCase):
    def test_enabling_and_disabling_2fa_signs_out_other_sessions(self):
        user = _user()
        other = Client()
        other.force_login(user)
        self.assertEqual(other.get(reverse("accounts:settings")).status_code, 200)

        self.client.force_login(user)
        self.client.post(reverse("accounts:totp_start"))
        from accounts.views import _pending_totp_secret

        class _Req:
            session = self.client.session
        secret = _pending_totp_secret(_Req())
        done = self.client.post(reverse("accounts:totp_confirm"), {"code": pyotp.TOTP(secret).now()})
        self.assertEqual(done.status_code, 200)
        self.assertEqual(self.client.get(reverse("accounts:settings")).status_code, 200)
        self.assertEqual(other.get(reverse("accounts:settings")).status_code, 302)

        other.force_login(UserModel.objects.get(pk=user.pk))
        self.client.post(reverse("accounts:totp_disable"), {"password": "securepass1!"})
        self.assertEqual(self.client.get(reverse("accounts:settings")).status_code, 200)
        self.assertEqual(other.get(reverse("accounts:settings")).status_code, 302)

    def test_empty_stamp_keeps_existing_sessions_valid(self):
        user = _user()
        self.assertEqual(user.security_stamp, "")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("accounts:settings")).status_code, 200)


class HashedVerificationCodeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _user()

    def test_raw_code_is_never_stored(self):
        record = generate_code(self.user, "login_2fa")
        row = VerificationCode.objects.get(pk=record.pk)
        self.assertEqual(len(row.code_hash), 64)
        self.assertNotIn(record.raw_code, row.code_hash)
        self.assertFalse(hasattr(row, "code"))

    def test_expired_code_is_rejected(self):
        record = generate_code(self.user, "password_reset")
        VerificationCode.objects.filter(pk=record.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertFalse(check_code(self.user, "password_reset", record.raw_code))

    def test_code_is_bound_to_user_and_purpose(self):
        record = generate_code(self.user, "login_2fa")
        other = _user("other@gmail.com")
        generate_code(other, "login_2fa")
        self.assertFalse(check_code(other, "login_2fa", record.raw_code))
        self.assertFalse(check_code(self.user, "password_reset", record.raw_code))
        self.assertTrue(check_code(self.user, "login_2fa", record.raw_code))

    def test_replay_after_success_is_rejected(self):
        record = generate_code(self.user, "login_2fa")
        self.assertTrue(check_code(self.user, "login_2fa", record.raw_code))
        self.assertFalse(check_code(self.user, "login_2fa", record.raw_code))

    def test_cooldown_returns_no_raw_code(self):
        generate_code(self.user, "login_2fa")
        again = generate_code(self.user, "login_2fa")
        self.assertIsNone(again.raw_code)


@override_settings(FIELD_ENCRYPTION_KEYS=[KEY_A])
class AdminSecondFactorTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = UserModel.objects.create_superuser(email="root@gmail.com", password="securepass1!")

    def test_admin_login_requires_totp_when_enabled(self):
        secret = _enable_totp(self.admin)
        response = self.client.post(reverse("admin_login"), {
            "email": self.admin.email, "password": "securepass1!",
        })
        self.assertRedirects(response, reverse("accounts:verify_totp"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.get(reverse("ops:overview")).status_code, 302)
        done = self.client.post(reverse("accounts:verify_totp"), {"code": pyotp.TOTP(secret).now()})
        self.assertRedirects(done, reverse("ops:overview"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("ops:overview")).status_code, 200)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", BREVO_API_KEY="",
    )
    def test_admin_login_requires_email_code_when_enabled(self):
        from django.core import mail
        import re

        self.admin.email_2fa_enabled = True
        self.admin.save()
        response = self.client.post(reverse("admin_login"), {
            "email": self.admin.email, "password": "securepass1!",
        })
        self.assertRedirects(response, reverse("accounts:verify_login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        done = self.client.post(reverse("accounts:verify_login"), {"code": code})
        self.assertRedirects(done, reverse("ops:overview"), fetch_redirect_response=False)

    def test_django_admin_login_redirects_to_cyberquest_sign_in(self):
        response = self.client.get("/admin/login/?next=/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("admin_login")))
        self.assertIn("next=/admin/", response["Location"])

    def test_student_cannot_use_admin_sign_in(self):
        student = _user("student@gmail.com")
        response = self.client.post(reverse("admin_login"), {
            "email": student.email, "password": "securepass1!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_staff_may_only_continue_to_django_admin(self):
        staff = _user("staff@gmail.com", is_staff=True)
        denied = self.client.post(reverse("admin_login"), {
            "email": staff.email, "password": "securepass1!",
        })
        self.assertEqual(denied.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        allowed = self.client.post(reverse("admin_login") + "?next=/admin/", {
            "email": staff.email, "password": "securepass1!", "next": "/admin/",
        })
        self.assertRedirects(allowed, "/admin/", fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("ops:overview")).status_code, 403)


class AdminSignInPageTests(TestCase):
    def test_page_has_labels_toggle_csrf_and_noindex(self):
        page = self.client.get(reverse("admin_login"))
        self.assertEqual(page.status_code, 200)
        for snippet in (
            '<label for="id_email">', '<label for="id_password">',
            'autocomplete="current-password"', 'aria-controls="id_password"', 'aria-pressed="false"',
            'name="csrfmiddlewaretoken"', '<meta name="robots" content="noindex, nofollow">',
        ):
            self.assertContains(page, snippet, html=False)

    def test_errors_are_announced(self):
        cache.clear()
        page = self.client.post(reverse("admin_login"), {"email": "nobody@example.com", "password": "x"})
        self.assertContains(page, 'role="alert"')
        self.assertContains(page, "Invalid email or password.")


class LogoutMethodTests(TestCase):
    """P1-01: logout_view must only accept POST."""

    def setUp(self):
        self.user = _user("logout_test@example.com")
        self.client.force_login(self.user)

    def test_get_returns_405(self):
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)

    def test_post_logs_out_and_redirects(self):
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, "/", fetch_redirect_response=False)
        # Session should be cleared
        self.assertNotIn("_auth_user_id", self.client.session)
