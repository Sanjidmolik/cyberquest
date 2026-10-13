"""Data export, account deletion, retention cleanup, and legal pages."""

import io
import json
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path

import pyotp
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.codes import generate_code
from accounts.models import VerificationCode
from accounts.retention import run_all
from games.models import GameAttempt
from notifications.models import Notification

UserModel = get_user_model()
KEY = Fernet.generate_key().decode()
PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _user(email, **extra):
    return UserModel.objects.create_user(
        email=email, password="securepass1!", username=email.split("@")[0], ethical_agreement=True, **extra,
    )


def _attempt(user, game="phishing_simulator"):
    return GameAttempt.objects.create(user=user, game_key=game, score=4, total_questions=5, xp_awarded=40)


@override_settings(FIELD_ENCRYPTION_KEYS=[KEY])
class DataExportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.alice = _user("alice@example.com", full_name="Alice A")
        self.bob = _user("bob@example.com", full_name="Bob B")
        self.alice_attempt = _attempt(self.alice)
        self.bob_attempt = _attempt(self.bob, "cryptography")
        Notification.objects.create(user=self.bob, message="Bob private note")
        self.alice.set_totp_secret(pyotp.random_base32())
        self.alice.totp_enabled = True
        self.alice.save()
        self.secret = self.alice.get_totp_secret()
        generate_code(self.alice, "login_2fa")

    def test_export_requires_login_and_post(self):
        url = reverse("accounts:data_export")
        self.assertEqual(self.client.post(url).status_code, 302)
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_json_export_contains_only_own_data_and_no_secrets(self):
        self.client.force_login(self.alice)
        response = self.client.post(reverse("accounts:data_export"), {"format": "json"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "no-store, private")
        body = response.content.decode("utf-8")
        data = json.loads(body)
        self.assertEqual(data["profile"]["email"], "alice@example.com")
        self.assertEqual([a["id"] for a in data["mission_attempts"]], [self.alice_attempt.pk])
        self.assertNotIn("bob@example.com", body)
        self.assertNotIn("Bob private note", body)
        alice = UserModel.objects.get(pk=self.alice.pk)
        for secret in (alice.password, alice.totp_secret, self.secret,
                       VerificationCode.objects.get(user=alice).code_hash):
            self.assertNotIn(secret, body)
        for field in ("password", "totp_secret", "security_stamp", "totp_last_used_step"):
            self.assertNotIn(field, data["profile"])

    def test_csv_export_is_a_zip_of_tables_with_picture(self):
        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            self.alice.profile_picture.save("a.png", SimpleUploadedFile("a.png", PNG_1PX), save=True)
            self.client.force_login(self.alice)
            response = self.client.post(reverse("accounts:data_export"), {"format": "csv"})
            self.assertEqual(response["Content-Type"], "application/zip")
            bundle = zipfile.ZipFile(io.BytesIO(response.content))
            names = set(bundle.namelist())
            self.assertTrue({"profile.csv", "mission_attempts.csv", "badges.csv", "profile_picture.png"} <= names)
            attempts = bundle.read("mission_attempts.csv").decode("utf-8-sig")
            self.assertIn("phishing_simulator", attempts)
            self.assertNotIn("cryptography", attempts)


@override_settings(FIELD_ENCRYPTION_KEYS=[KEY])
class AccountDeletionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _user("leaver@example.com")
        self.attempt = _attempt(self.user)
        self.url = reverse("accounts:delete_account")

    def test_get_shows_confirmation_and_deletes_nothing(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.url), "Permanently delete account")
        self.assertTrue(UserModel.objects.filter(pk=self.user.pk).exists())

    def test_csrf_token_is_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(self.url, {"password": "securepass1!", "confirm": "DELETE"})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(UserModel.objects.filter(pk=self.user.pk).exists())

    def test_wrong_password_or_phrase_is_refused(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url, {"password": "nope", "confirm": "DELETE"}).status_code, 400)
        self.assertEqual(self.client.post(self.url, {"password": "securepass1!", "confirm": "delete"}).status_code, 400)
        self.assertTrue(UserModel.objects.filter(pk=self.user.pk).exists())

    def test_deletion_removes_data_files_and_every_session(self):
        from certificates.models import IssuedCertificate

        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            self.user.profile_picture.save("p.png", SimpleUploadedFile("p.png", PNG_1PX), save=True)
            picture = Path(media) / self.user.profile_picture.name
            cert = IssuedCertificate(user=self.user, certificate_id="CQ-2026-DEL000000001",
                                     verification_token="d" * 40, recipient_name="Leaver", score=90,
                                     issued_at=timezone.now())
            cert.pdf_file.save("CQ-2026-DEL000000001.pdf", SimpleUploadedFile("c.pdf", b"%PDF-1.4"), save=True)
            pdf = Path(media) / cert.pdf_file.name
            self.assertTrue(picture.is_file() and pdf.is_file())

            other = Client()
            other.force_login(self.user)
            self.client.force_login(self.user)
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url, {"password": "securepass1!", "confirm": "DELETE"})
            self.assertRedirects(response, reverse("pages:home"))

            self.assertFalse(UserModel.objects.filter(pk=self.user.pk).exists())
            self.assertFalse(GameAttempt.objects.filter(pk=self.attempt.pk).exists())
            self.assertFalse(IssuedCertificate.objects.filter(pk=cert.pk).exists())
            self.assertFalse(picture.exists())
            self.assertFalse(pdf.exists())
            self.assertNotIn("_auth_user_id", self.client.session)
            self.assertEqual(other.get(reverse("accounts:settings")).status_code, 302)

    def test_totp_code_is_required_when_enabled(self):
        secret = pyotp.random_base32()
        self.user.set_totp_secret(secret)
        self.user.totp_enabled = True
        self.user.save()
        self.client.force_login(self.user)
        refused = self.client.post(self.url, {"password": "securepass1!", "confirm": "DELETE", "code": "000000"})
        self.assertEqual(refused.status_code, 400)
        self.client.post(self.url, {"password": "securepass1!", "confirm": "DELETE",
                                    "code": pyotp.TOTP(secret).now()})
        self.assertFalse(UserModel.objects.filter(pk=self.user.pk).exists())

    def test_google_only_account_needs_recent_sign_in(self):
        google = UserModel.objects.create_user(email="g@example.com", username="g", google_linked=True)
        self.client.force_login(google)
        UserModel.objects.filter(pk=google.pk).update(last_login=timezone.now() - timedelta(hours=2))
        self.assertEqual(self.client.post(self.url, {"confirm": "DELETE"}).status_code, 400)
        UserModel.objects.filter(pk=google.pk).update(last_login=timezone.now())
        self.client.post(self.url, {"confirm": "DELETE"})
        self.assertFalse(UserModel.objects.filter(pk=google.pk).exists())

    def test_administrators_cannot_self_delete(self):
        admin = UserModel.objects.create_superuser(email="root@example.com", password="securepass1!")
        self.client.force_login(admin)
        self.client.post(self.url, {"password": "securepass1!", "confirm": "DELETE"})
        self.assertTrue(UserModel.objects.filter(pk=admin.pk).exists())

    def test_one_user_cannot_delete_another(self):
        other = _user("victim@example.com")
        self.client.force_login(self.user)
        self.client.post(self.url, {"password": "securepass1!", "confirm": "DELETE", "user": other.pk})
        self.assertTrue(UserModel.objects.filter(pk=other.pk).exists())


class RetentionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_purge_removes_only_expired_data_and_is_idempotent(self):
        now = timezone.now()
        keeper = _user("keeper@example.com")
        old = generate_code(keeper, "login_2fa")
        VerificationCode.objects.filter(pk=old.pk).update(expires_at=now - timedelta(days=8))
        cache.clear()
        fresh = generate_code(keeper, "password_reset")

        stale = _user("stale@example.com", email_verified=False, is_active=False)
        UserModel.objects.filter(pk=stale.pk).update(date_joined=now - timedelta(days=31))
        recent = _user("recent@example.com", email_verified=False, is_active=False)
        verified_old = _user("verified@example.com")
        UserModel.objects.filter(pk=verified_old.pk).update(date_joined=now - timedelta(days=400))

        expired = SessionStore()
        expired["x"] = 1
        expired.create()
        Session.objects.filter(session_key=expired.session_key).update(expire_date=now - timedelta(days=1))
        live = SessionStore()
        live["x"] = 1
        live.create()

        dry = run_all(dry_run=True)
        self.assertEqual(dry["verification_codes"], 1)
        self.assertTrue(VerificationCode.objects.filter(pk=old.pk).exists())

        first = run_all()
        self.assertEqual(first["verification_codes"], 1)
        self.assertEqual(first["unverified_signups"], 1)
        self.assertEqual(first["expired_sessions"], 1)
        self.assertFalse(VerificationCode.objects.filter(pk=old.pk).exists())
        self.assertTrue(VerificationCode.objects.filter(pk=fresh.pk).exists())
        self.assertFalse(UserModel.objects.filter(pk=stale.pk).exists())
        self.assertTrue(UserModel.objects.filter(pk__in=[recent.pk, verified_old.pk, keeper.pk]).count() == 3)
        self.assertTrue(Session.objects.filter(session_key=live.session_key).exists())

        second = run_all()
        self.assertEqual(sum(v for k, v in second.items() if k != "expired_cache_entries"), 0)

    def test_management_command_runs(self):
        out = io.StringIO()
        call_command("purge_expired_data", "--dry-run", stdout=out)
        self.assertIn("would remove", out.getvalue())


class LegalPageTests(TestCase):
    def test_pages_render_and_are_linked(self):
        for name in ("pages:privacy", "pages:terms", "pages:notices"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)
        about = self.client.get(reverse("pages:about"))
        self.assertContains(about, reverse("pages:privacy"))
        self.assertContains(about, reverse("pages:terms"))
        signup = self.client.get(reverse("accounts:signup"))
        self.assertContains(signup, reverse("pages:privacy"))
        self.assertContains(signup, reverse("pages:terms"))
        home = self.client.get(reverse("pages:home"))
        self.assertContains(home, reverse("pages:privacy"))

    def test_settings_links_to_export_and_deletion(self):
        user = _user("links@example.com")
        self.client.force_login(user)
        page = self.client.get(reverse("accounts:settings"))
        self.assertContains(page, reverse("accounts:data_export"))
        self.assertContains(page, reverse("accounts:delete_account"))
        self.assertContains(page, reverse("pages:privacy"))

    @override_settings(SOURCE_CODE_URL="https://github.com/example/cyberquest", SOURCE_CODE_REVISION="abc123def4567890")
    def test_notices_page_offers_running_source(self):
        page = self.client.get(reverse("pages:notices"))
        self.assertContains(page, "https://github.com/example/cyberquest/tree/abc123def4567890")
        self.assertContains(page, "AGPL-3.0")

    def test_privacy_policy_lists_retention_rows(self):
        from accounts.retention import RETENTION

        page = self.client.get(reverse("pages:privacy"))
        for record, _kept, _removal in RETENTION:
            self.assertContains(page, record.split(" (")[0])
