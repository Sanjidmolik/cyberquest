from datetime import date, timedelta
from io import BytesIO
import re
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

UserModel = get_user_model()


def _make_image(fmt="JPEG", size=(64, 64), color=(20, 180, 200)):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    buffer.seek(0)
    ext = "jpg" if fmt == "JPEG" else fmt.lower()
    content_type = "image/jpeg" if fmt == "JPEG" else f"image/{ext}"
    return SimpleUploadedFile(f"avatar.{ext}", buffer.read(), content_type=content_type)


def _signup_data(**overrides):
    payload = {
        "username": "newrecruit",
        "email": "new.recruit@gmail.com",
        "password": "securepass1!",
        "confirm_password": "securepass1!",
        "date_of_birth": "2000-01-15",
        "cyber_class": "general",
        "skill_level": "beginner",
        "ethical_agreement": "on",
    }
    payload.update(overrides)
    return payload


def _latest_code():
    match = re.search(r"\b(\d{6})\b", mail.outbox[-1].body)
    return match.group(1)


class ProfileSettingsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = UserModel.objects.create_user(
            email="recruit@gmail.com",
            password="securepass1",
            username="recruit",
            full_name="Recruit One",
            date_of_birth=date(2000, 1, 15),
            cyber_class="general",
            skill_level="beginner",
            ethical_agreement=True,
            course_intro_completed=True,
        )
        self.other = UserModel.objects.create_user(
            email="other@gmail.com",
            password="securepass1",
            username="otheruser",
            ethical_agreement=True,
            course_intro_completed=True,
        )
        self.url = reverse("accounts:settings")
        self._media_dir = tempfile.TemporaryDirectory()
        self._media_override = override_settings(MEDIA_ROOT=self._media_dir.name)
        self._media_override.enable()
        self.addCleanup(self._media_override.disable)
        self.addCleanup(self._media_dir.cleanup)

    def test_login_required(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_logged_in_can_open_settings(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profile Settings")
        self.assertContains(response, "recruit@gmail.com")
        self.assertContains(response, "Email is used for login")

    def test_update_personal_fields(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            "full_name": "Updated Name",
            "username": "newhandle",
            "date_of_birth": "1999-05-20",
            "cyber_class": "ethical_hacker",
            "skill_level": "intermediate",
        })
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "Updated Name")
        self.assertEqual(self.user.username, "newhandle")
        self.assertEqual(self.user.date_of_birth, date(1999, 5, 20))
        self.assertEqual(self.user.cyber_class, "ethical_hacker")
        self.assertEqual(self.user.skill_level, "intermediate")
        self.assertEqual(self.user.email, "recruit@gmail.com")
        self.assertEqual(self.user.xp, 0)
        self.assertFalse(self.user.is_staff)

    def test_duplicate_username_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            "full_name": "Recruit One",
            "username": "otheruser",
            "date_of_birth": "2000-01-15",
            "cyber_class": "general",
            "skill_level": "beginner",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That username is already taken.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "recruit")

    def test_same_username_allowed_for_self(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {
            "full_name": "Recruit One",
            "username": "recruit",
            "date_of_birth": "2000-01-15",
            "cyber_class": "osint",
            "skill_level": "advanced",
        })
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.cyber_class, "osint")

    def test_cannot_edit_another_user(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {
            "full_name": "Hacked",
            "username": "recruit",
            "date_of_birth": "2000-01-15",
            "cyber_class": "general",
            "skill_level": "beginner",
        })
        self.other.refresh_from_db()
        self.assertNotEqual(self.other.full_name, "Hacked")
        self.assertEqual(self.other.username, "otheruser")

    def test_upload_and_remove_profile_picture(self):
        self.client.force_login(self.user)
        upload = _make_image()
        response = self.client.post(self.url, {
            "full_name": "Recruit One",
            "username": "recruit",
            "date_of_birth": "2000-01-15",
            "cyber_class": "general",
            "skill_level": "beginner",
            "profile_picture": upload,
        })
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertTrue(bool(self.user.profile_picture))
        picture_name = self.user.profile_picture.name
        self.assertTrue(Path(self._media_dir.name, picture_name).exists())

        response = self.client.post(self.url, {"remove_photo": "1"})
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertFalse(bool(self.user.profile_picture))
        self.assertFalse(Path(self._media_dir.name, picture_name).exists())

    def test_invalid_image_rejected(self):
        self.client.force_login(self.user)
        fake = SimpleUploadedFile("evil.txt", b"not-an-image", content_type="text/plain")
        response = self.client.post(self.url, {
            "full_name": "Recruit One",
            "username": "recruit",
            "date_of_birth": "2000-01-15",
            "cyber_class": "general",
            "skill_level": "beginner",
            "profile_picture": fake,
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(bool(self.user.profile_picture))

    def test_profile_photo_requires_login_and_serves_that_user_only(self):
        from io import BytesIO

        from django.core.files.base import ContentFile
        from PIL import Image

        buffer = BytesIO()
        Image.new("RGB", (8, 8), (9, 8, 7)).save(buffer, format="PNG")
        self.user.profile_picture.save("face.png", ContentFile(buffer.getvalue()), save=True)
        anon = Client()
        denied = anon.get(reverse("accounts:profile_photo", args=[self.user.pk]))
        self.assertEqual(denied.status_code, 302)
        self.assertIn("/accounts/login/", denied.url)
        self.client.force_login(self.user)
        photo = self.client.get(reverse("accounts:profile_photo", args=[self.user.pk]))
        self.assertEqual(photo.status_code, 200)
        self.assertEqual(photo["Content-Type"], "image/png")
        self.assertTrue(b"".join(photo.streaming_content).startswith(b"\x89PNG"))
        photo.close()
        missing = self.client.get(reverse("accounts:profile_photo", args=[self.other.pk]))
        self.assertEqual(missing.status_code, 404)
        settings_page = self.client.get(self.url)
        self.assertContains(settings_page, reverse("accounts:profile_photo", args=[self.user.pk]))

    def test_oversized_image_rejected(self):
        self.client.force_login(self.user)
        big = SimpleUploadedFile(
            "big.jpg",
            b"\xff\xd8\xff" + (b"0" * (5 * 1024 * 1024 + 10)),
            content_type="image/jpeg",
        )
        response = self.client.post(self.url, {
            "full_name": "Recruit One",
            "username": "recruit",
            "date_of_birth": "2000-01-15",
            "cyber_class": "general",
            "skill_level": "beginner",
            "profile_picture": big,
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(bool(self.user.profile_picture))

    def test_email_not_editable_via_post(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {
            "full_name": "Recruit One",
            "username": "recruit",
            "email": "attacker@gmail.com",
            "date_of_birth": "2000-01-15",
            "cyber_class": "general",
            "skill_level": "beginner",
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "recruit@gmail.com")

    def test_email_login_code_is_off_until_chosen(self):
        self.client.force_login(self.user)
        page = self.client.get(self.url)
        self.assertContains(page, "Email login code")
        self.assertContains(page, "Turn on email codes")
        self.assertFalse(self.user.email_2fa_enabled)

        on = self.client.post(reverse("accounts:email_2fa_toggle"), {"enabled": "1"})
        self.assertRedirects(on, self.url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_2fa_enabled)

        off = self.client.post(reverse("accounts:email_2fa_toggle"), {"enabled": "0"})
        self.assertRedirects(off, self.url)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_2fa_enabled)


class VerificationCodeSecurityTests(TestCase):
    def setUp(self):
        self.user = UserModel.objects.create_user(
            email="codes@gmail.com",
            password="securepass1",
            username="codesuser",
            ethical_agreement=True,
        )

    def test_code_uses_secrets_and_is_single_use(self):
        from accounts.codes import check_code, generate_code

        record = generate_code(self.user, purpose="login_2fa")
        self.assertEqual(len(record.code), 6)
        self.assertTrue(record.code.isdigit())
        self.assertTrue(check_code(self.user, purpose="login_2fa", submitted_code=record.code))
        self.assertFalse(check_code(self.user, purpose="login_2fa", submitted_code=record.code))

    def test_code_burns_after_too_many_failures(self):
        from accounts.codes import MAX_ATTEMPTS, check_code, generate_code

        record = generate_code(self.user, purpose="password_reset")
        for _ in range(MAX_ATTEMPTS):
            self.assertFalse(
                check_code(self.user, purpose="password_reset", submitted_code="000000")
            )
        record.refresh_from_db()
        self.assertTrue(record.is_used)
        self.assertFalse(
            check_code(self.user, purpose="password_reset", submitted_code=record.code)
        )


class AuthFlowFixTests(TestCase):
    def test_login_and_signup_pages_drop_the_site_nav(self):
        login_page = self.client.get(reverse("accounts:login"))
        signup_page = self.client.get(reverse("accounts:signup"))
        self.assertNotContains(login_page, 'id="cq-nav"')
        self.assertNotContains(signup_page, 'id="cq-nav"')
        self.assertContains(login_page, "Create an account")
        self.assertNotContains(login_page, "Administrator sign in")
        self.assertNotContains(login_page, reverse("accounts:admin_login"))
        self.assertContains(signup_page, "Sign up with Google")
        self.assertContains(signup_page, "Create Account")

    def test_login_and_signup_styles_keep_a_keyboard_focus_ring(self):
        login_css = (settings.BASE_DIR / "accounts/static/accounts/css/login_v2.css").read_text(encoding="utf-8")
        theme_css = (settings.BASE_DIR / "static/shared/css/theme.css").read_text(encoding="utf-8")
        self.assertIn(".lq-input:focus-visible", login_css)
        self.assertIn(".lq-btn:focus-visible", login_css)
        self.assertIn("outline-color: #fff", login_css)
        self.assertIn(".cq-shell input.cq-input:focus-visible", theme_css)
        self.assertIn(".cq-choice-card:focus-within", theme_css)
        self.assertIn("outline-color: #4c1d95", theme_css)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_signup_lands_on_the_dashboard(self):
        cache.clear()
        response = self.client.post(reverse("accounts:signup"), _signup_data())
        self.assertRedirects(response, reverse("accounts:verify_email"))
        self.assertNotIn("_auth_user_id", self.client.session)
        user = UserModel.objects.get(email="new.recruit@gmail.com")
        self.assertFalse(user.email_verified)
        self.assertFalse(user.is_active)
        verified = self.client.post(reverse("accounts:verify_email"), {"code": _latest_code()})
        self.assertRedirects(verified, reverse("dashboard:home"))
        self.assertNotEqual(verified.url, reverse("courses:intro"))
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertTrue(user.is_active)

    def test_admin_login_is_superuser_only_and_rejects_open_redirects(self):
        student = UserModel.objects.create_user(
            email="student.login@gmail.com", password="securepass1", username="studentlogin",
            ethical_agreement=True,
        )
        staff = UserModel.objects.create_user(
            email="staff.login@gmail.com", password="securepass1", username="stafflogin",
            is_staff=True, ethical_agreement=True,
        )
        admin = UserModel.objects.create_superuser(
            email="root.login@gmail.com", password="securepass1", username="rootlogin",
        )
        page = self.client.get("/admin-login/")
        self.assertContains(page, "Administrator sign in")
        self.assertEqual(page.request["PATH_INFO"], "/admin-login/")
        aliased = self.client.get(reverse("accounts:admin_login"))
        self.assertContains(aliased, "Administrator sign in")
        denied = self.client.post(reverse("accounts:admin_login"), {
            "email": student.email, "password": "securepass1",
        })
        self.assertEqual(denied.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        staff_denied = self.client.post(reverse("accounts:admin_login"), {
            "email": staff.email, "password": "securepass1",
        })
        self.assertEqual(staff_denied.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        away = self.client.post(reverse("accounts:admin_login"), {
            "email": admin.email,
            "password": "securepass1",
            "next": "https://evil.example/phish",
        })
        self.assertRedirects(away, reverse("ops:overview"))
        self.assertNotIn("evil.example", away.url)

        secure = self.client.__class__(enforce_csrf_checks=True)
        blocked = secure.post(reverse("accounts:admin_login"), {
            "email": admin.email, "password": "securepass1",
        })
        self.assertEqual(blocked.status_code, 403)

    def test_google_profile_completion_and_linking(self):
        from unittest.mock import patch

        existing = UserModel.objects.create_user(
            email="linked@gmail.com", password="securepass1", username="linkeduser",
            ethical_agreement=True,
        )
        session = self.client.session
        session["google_oauth_state"] = "state-1"
        session.save()
        with patch("accounts.views.exchange_code_for_token", return_value={"access_token": "token"}), \
             patch("accounts.views.fetch_google_userinfo", return_value={
                 "email": "linked@gmail.com", "email_verified": True, "name": "Linked User",
             }):
            linked = self.client.get(reverse("accounts:google_callback"), {"code": "c", "state": "state-1"})
        self.assertRedirects(linked, reverse("dashboard:home"))
        existing.refresh_from_db()
        self.assertTrue(existing.google_linked)
        self.assertTrue(existing.check_password("securepass1"))
        self.assertEqual(UserModel.objects.filter(email__iexact="linked@gmail.com").count(), 1)

        self.client.logout()
        session = self.client.session
        session["google_oauth_state"] = "state-2"
        session.save()
        with patch("accounts.views.exchange_code_for_token", return_value={"access_token": "token"}), \
             patch("accounts.views.fetch_google_userinfo", return_value={
                 "email": "fresh.google@gmail.com", "email_verified": True, "name": "Fresh Google",
             }):
            created = self.client.get(reverse("accounts:google_callback"), {"code": "c", "state": "state-2"})
        self.assertRedirects(created, reverse("accounts:complete_profile"))
        fresh = UserModel.objects.get(email="fresh.google@gmail.com")
        self.assertTrue(fresh.google_linked)
        self.assertFalse(fresh.has_usable_password())
        UserModel.objects.create_user(email="other@gmail.com", password="securepass1", username="takenname")
        collision = self.client.post(reverse("accounts:complete_profile"), {
            "username": "takenname",
            "date_of_birth": "2000-01-15",
            "cyber_class": "general",
            "skill_level": "beginner",
            "ethical_agreement": "on",
        })
        self.assertEqual(collision.status_code, 200)
        self.assertContains(collision, "That username is already taken.")
        finished = self.client.post(reverse("accounts:complete_profile"), {
            "username": "freshgoogle",
            "date_of_birth": "2000-01-15",
            "cyber_class": "general",
            "skill_level": "beginner",
            "ethical_agreement": "on",
        })
        self.assertRedirects(finished, reverse("dashboard:home"))
        fresh.refresh_from_db()
        self.assertEqual(fresh.username, "freshgoogle")
        self.assertTrue(fresh.ethical_agreement)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SignupVerificationTests(TestCase):
    def setUp(self):
        cache.clear()

    def _start(self, **overrides):
        response = self.client.post(reverse("accounts:signup"), _signup_data(**overrides))
        self.assertRedirects(response, reverse("accounts:verify_email"))
        return UserModel.objects.get(email=overrides.get("email", "new.recruit@gmail.com"))

    def test_wrong_expired_reused_and_resent_codes(self):
        user = self._start()
        self.assertFalse(user.email_verified)
        wrong = self.client.post(reverse("accounts:verify_email"), {"code": "000000"})
        self.assertEqual(wrong.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertNotIn("_auth_user_id", self.client.session)

        record = user.verification_codes.get()
        record.expires_at = timezone.now() - timedelta(minutes=1)
        record.save(update_fields=["expires_at"])
        expired = self.client.post(reverse("accounts:verify_email"), {"code": record.code})
        self.assertEqual(expired.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)

        cache.clear()
        resent = self.client.post(reverse("accounts:verify_email"), {"resend": "1"})
        self.assertEqual(resent.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
        old_code = record.code
        new_code = _latest_code()
        self.assertNotEqual(old_code, new_code)
        reused = self.client.post(reverse("accounts:verify_email"), {"code": old_code})
        self.assertEqual(reused.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)
        done = self.client.post(reverse("accounts:verify_email"), {"code": new_code})
        self.assertRedirects(done, reverse("dashboard:home"))
        used = user.verification_codes.order_by("-created_at").first()
        self.assertTrue(used.is_used)
        self.client.logout()
        session = self.client.session
        session["pending_signup_user_id"] = user.pk
        session.save()
        reused_success = self.client.post(reverse("accounts:verify_email"), {"code": new_code})
        self.assertRedirects(reused_success, reverse("accounts:login"))

    def test_resend_cooldown_and_duplicate_signup(self):
        user = self._start()
        resent = self.client.post(reverse("accounts:verify_email"), {"resend": "1"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(resent, "Please wait a moment before requesting another code.")
        again = self.client.post(reverse("accounts:signup"), _signup_data(username="newrecruit"))
        self.assertRedirects(again, reverse("accounts:verify_email"))
        self.assertEqual(UserModel.objects.filter(email__iexact="new.recruit@gmail.com").count(), 1)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)

    def test_smtp_failure_does_not_claim_the_email_was_sent(self):
        from unittest.mock import patch
        with patch("accounts.emails.send_mail", side_effect=OSError("smtp down")):
            response = self.client.post(
                reverse("accounts:signup"),
                _signup_data(email="smtp.fail@gmail.com", username="smtpfail"),
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:verify_email"))
        page = self.client.get(reverse("accounts:verify_email"))
        self.assertContains(page, "could not send the verification email")
        self.assertNotContains(page, "We sent a verification code")
        user = UserModel.objects.get(email="smtp.fail@gmail.com")
        self.assertFalse(user.email_verified)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_smtp_timeout_keeps_signup_unverified_with_a_resend_path(self):
        from unittest.mock import patch

        from django.core.mail import get_connection

        with override_settings(EMAIL_TIMEOUT=8, EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"):
            self.assertEqual(get_connection().timeout, 8)
        with patch("accounts.emails.send_mail", side_effect=TimeoutError("timed out")):
            response = self.client.post(
                reverse("accounts:signup"),
                _signup_data(email="smtp.timeout@gmail.com", username="smtptimeout"),
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:verify_email"))
        page = self.client.get(reverse("accounts:verify_email"))
        self.assertContains(page, "could not send the verification email")
        self.assertContains(page, 'name="resend"')
        self.assertNotContains(page, "We sent a verification code")
        user = UserModel.objects.get(email="smtp.timeout@gmail.com")
        self.assertFalse(user.email_verified)
        self.assertFalse(user.is_active)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_welcome_email_timeout_does_not_fail_verified_signup(self):
        from unittest.mock import patch

        user = self._start(email="welcome.timeout@gmail.com", username="welcometimeout")
        code = _latest_code()
        with patch("accounts.emails.send_mail", side_effect=TimeoutError("timed out")):
            done = self.client.post(reverse("accounts:verify_email"), {"code": code})
        self.assertEqual(done.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertTrue(user.is_active)
        self.assertIn("_auth_user_id", self.client.session)

    def test_google_cannot_bypass_unverified_signup(self):
        from unittest.mock import patch
        user = self._start(email="pending.google@gmail.com", username="pendinggoogle")
        self.client.logout()
        session = self.client.session
        session["google_oauth_state"] = "state-pending"
        session.save()
        with patch("accounts.views.exchange_code_for_token", return_value={"access_token": "token"}), \
             patch("accounts.views.fetch_google_userinfo", return_value={
                 "email": "pending.google@gmail.com", "email_verified": True, "name": "Pending",
             }):
            blocked = self.client.get(reverse("accounts:google_callback"), {"code": "c", "state": "state-pending"})
        self.assertRedirects(blocked, reverse("accounts:verify_email"))
        self.assertNotIn("_auth_user_id", self.client.session)
        user.refresh_from_db()
        self.assertFalse(user.email_verified)
        self.assertFalse(user.google_linked)
        self.assertFalse(user.is_active)

    def test_password_policy_on_signup_and_reset(self):
        short = self.client.post(reverse("accounts:signup"), _signup_data(password="Ab1!", confirm_password="Ab1!"))
        self.assertEqual(short.status_code, 200)
        self.assertContains(short, "at least 8 characters")
        plain = self.client.post(reverse("accounts:signup"), _signup_data(password="securepass1", confirm_password="securepass1"))
        self.assertEqual(plain.status_code, 200)
        self.assertContains(plain, "special character")
        self.assertFalse(UserModel.objects.filter(email="new.recruit@gmail.com").exists())

        user = UserModel.objects.create_user(
            email="reset.me@gmail.com", password="securepass1!", username="resetme", ethical_agreement=True,
        )
        from accounts.codes import generate_code
        record = generate_code(user, purpose="password_reset")
        session = self.client.session
        session["pending_reset_user_id"] = user.pk
        session.save()
        rejected = self.client.post(reverse("accounts:reset_password"), {
            "code": record.code,
            "new_password": "securepass1",
            "confirm_password": "securepass1",
        })
        self.assertEqual(rejected.status_code, 200)
        self.assertContains(rejected, "special character")
        user.refresh_from_db()
        self.assertTrue(user.check_password("securepass1!"))
        record.refresh_from_db()
        self.assertFalse(record.is_used)
        accepted = self.client.post(reverse("accounts:reset_password"), {
            "code": record.code,
            "new_password": "betterpass1!",
            "confirm_password": "betterpass1!",
        })
        self.assertRedirects(accepted, reverse("accounts:login"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("betterpass1!"))

    def test_signup_can_retry_after_smtp_failure(self):
        from unittest.mock import patch

        with patch("accounts.emails.send_mail", side_effect=OSError("smtp down")) as send:
            failed = self.client.post(
                reverse("accounts:signup"),
                _signup_data(email="retry.signup@gmail.com", username="retrysignup"),
            )
        self.assertEqual(failed.status_code, 302)
        self.assertFalse(send.call_args.kwargs["fail_silently"])
        user = UserModel.objects.get(email="retry.signup@gmail.com")
        self.assertFalse(user.email_verified)
        self.assertFalse(user.is_active)
        resent = self.client.post(reverse("accounts:verify_email"), {"resend": "1"})
        self.assertEqual(resent.status_code, 200)
        self.assertContains(resent, "We sent a verification code")
        verified = self.client.post(reverse("accounts:verify_email"), {"code": _latest_code()})
        self.assertRedirects(verified, reverse("dashboard:home"))
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertTrue(user.is_active)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AuthMailFailureTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = UserModel.objects.create_user(
            email="mail.fail@gmail.com",
            password="securepass1!",
            username="mailfail",
            ethical_agreement=True,
            email_2fa_enabled=True,
        )

    def test_login_code_smtp_failure_does_not_sign_in_and_can_retry(self):
        from unittest.mock import patch

        from accounts.views import RESET_REQUEST_MESSAGE

        with patch("accounts.emails.send_mail", side_effect=OSError("smtp down")) as send:
            failed = self.client.post(reverse("accounts:login"), {
                "email": self.user.email,
                "password": "securepass1!",
            })
        self.assertEqual(failed.status_code, 200)
        self.assertFalse(send.call_args.kwargs["fail_silently"])
        self.assertContains(failed, "could not send the login verification email")
        self.assertNotContains(failed, "A new code has been sent")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("pending_2fa_user_id", self.client.session)

        retried = self.client.post(reverse("accounts:login"), {
            "email": self.user.email,
            "password": "securepass1!",
        })
        self.assertRedirects(retried, reverse("accounts:verify_login"))
        self.assertNotIn("_auth_user_id", self.client.session)
        denied = self.client.post(reverse("accounts:verify_login"), {"code": "000000"})
        self.assertEqual(denied.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        allowed = self.client.post(reverse("accounts:verify_login"), {"code": _latest_code()})
        self.assertEqual(allowed.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

        self.client.logout()
        with patch("accounts.emails.send_mail", side_effect=OSError("smtp down")):
            missing = self.client.post(reverse("accounts:forgot_password"), {
                "email": "nobody.reset@gmail.com",
            }, follow=True)
            failed_reset = self.client.post(reverse("accounts:forgot_password"), {
                "email": self.user.email,
            }, follow=True)
        self.assertContains(missing, RESET_REQUEST_MESSAGE)
        self.assertContains(failed_reset, RESET_REQUEST_MESSAGE)
        self.assertContains(missing, "Please request a password reset code first.")
        self.assertContains(failed_reset, "Please request a password reset code first.")
        self.assertNotContains(failed_reset, "has been sent")
        self.assertNotContains(failed_reset, self.user.email)
        self.assertNotContains(missing, "nobody.reset@gmail.com")
        self.assertNotIn("pending_reset_user_id", self.client.session)
        burned = self.user.verification_codes.filter(purpose="password_reset").order_by("-created_at").first()
        self.assertIsNotNone(burned)
        self.assertTrue(burned.is_used)

        sent = self.client.post(reverse("accounts:forgot_password"), {
            "email": self.user.email,
        }, follow=True)
        self.assertContains(sent, "Reset Password")
        self.assertNotContains(sent, "Please request a password reset code first.")
        rejected = self.client.post(reverse("accounts:reset_password"), {
            "code": burned.code,
            "new_password": "otherpass1!",
            "confirm_password": "otherpass1!",
        })
        self.assertEqual(rejected.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("securepass1!"))
        accepted = self.client.post(reverse("accounts:reset_password"), {
            "code": _latest_code(),
            "new_password": "otherpass1!",
            "confirm_password": "otherpass1!",
        })
        self.assertRedirects(accepted, reverse("accounts:login"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("otherpass1!"))

    def test_login_code_resend_reports_smtp_failure(self):
        from unittest.mock import patch

        started = self.client.post(reverse("accounts:login"), {
            "email": self.user.email,
            "password": "securepass1!",
        })
        self.assertRedirects(started, reverse("accounts:verify_login"))
        with patch("accounts.emails.send_mail", side_effect=OSError("smtp down")):
            failed = self.client.post(reverse("accounts:verify_login"), {"resend": "1"})
        self.assertEqual(failed.status_code, 200)
        self.assertContains(failed, "could not send the login verification email")
        self.assertNotContains(failed, "A new code has been sent")
        self.assertNotIn("_auth_user_id", self.client.session)
        resent = self.client.post(reverse("accounts:verify_login"), {"resend": "1"})
        self.assertEqual(resent.status_code, 200)
        self.assertContains(resent, "A new code has been sent to your email.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_google_welcome_smtp_failure_still_finishes_sign_in(self):
        from unittest.mock import patch

        session = self.client.session
        session["google_oauth_state"] = "state-welcome"
        session.save()
        with patch("accounts.emails.send_mail", side_effect=TimeoutError("timed out")) as send, \
             patch("accounts.views.exchange_code_for_token", return_value={"access_token": "token"}), \
             patch("accounts.views.fetch_google_userinfo", return_value={
                 "email": "welcome.google@gmail.com",
                 "email_verified": True,
                 "name": "Welcome Google",
             }):
            created = self.client.get(
                reverse("accounts:google_callback"),
                {"code": "c", "state": "state-welcome"},
            )
        self.assertEqual(created.status_code, 302)
        self.assertFalse(send.call_args.kwargs["fail_silently"])
        self.assertEqual(send.call_count, 1)
        self.assertRedirects(created, reverse("accounts:complete_profile"))
        self.assertIn("_auth_user_id", self.client.session)
        user = UserModel.objects.get(email="welcome.google@gmail.com")
        self.assertTrue(user.google_linked)
        self.assertTrue(user.email_verified)
        self.assertEqual(mail.outbox, [])

    def test_requirements_pin_pyotp(self):
        import pyotp

        pinned = (settings.BASE_DIR / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("pyotp==2.9.0", pinned)
        self.assertTrue(pyotp.TOTP(pyotp.random_base32()).provisioning_uri(
            "recruit@gmail.com", issuer_name="CyberQuest"
        ))


@override_settings(BEHIND_RENDER_PROXY=False)
class ProxyRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = UserModel.objects.create_user(
            email="limit.user@gmail.com",
            password="securepass1!",
            username="limituser",
            ethical_agreement=True,
        )

    def _attempt(self, forwarded=None):
        extra = {}
        if forwarded is not None:
            extra["HTTP_X_FORWARDED_FOR"] = forwarded
        return self.client.post(reverse("accounts:login"), {
            "email": self.user.email,
            "password": "wrong-pass!",
        }, **extra)

    def test_forged_forwarded_header_does_not_reset_the_limit(self):
        for index in range(20):
            response = self._attempt(f"198.51.100.{index}")
            self.assertEqual(response.status_code, 200, index)
        blocked = self._attempt("203.0.113.50")
        self.assertRedirects(blocked, reverse("accounts:login"), fetch_redirect_response=False)
        page = self.client.get(reverse("accounts:login"))
        self.assertContains(page, "Too many attempts")

    @override_settings(BEHIND_RENDER_PROXY=True)
    def test_render_proxy_uses_the_rightmost_forwarded_address(self):
        for index in range(20):
            response = self._attempt(f"198.51.100.{index}, 203.0.113.10")
            self.assertEqual(response.status_code, 200, index)
        blocked = self._attempt("1.2.3.4, 203.0.113.10")
        self.assertRedirects(blocked, reverse("accounts:login"))
        other = self._attempt("203.0.113.10, 203.0.113.11")
        self.assertEqual(other.status_code, 200)
        self.assertContains(other, "Invalid email or password.")

    def test_limits_and_code_attempts_persist_in_the_database(self):
        from django.db import connection

        from accounts.codes import check_code, generate_code
        from cyberquest.ratelimit import is_rate_limited

        self.assertEqual(
            settings.CACHES["default"]["BACKEND"],
            "django.core.cache.backends.db.DatabaseCache",
        )
        self.assertFalse(is_rate_limited("rl:persist:203.0.113.8", limit=1, window_seconds=60))
        self.assertTrue(is_rate_limited("rl:persist:203.0.113.8", limit=1, window_seconds=60))
        record = generate_code(self.user, purpose="login_2fa")
        self.assertFalse(check_code(self.user, purpose="login_2fa", submitted_code="000000"))
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM cyberquest_cache WHERE cache_key LIKE %s",
                ["%rl:persist:203.0.113.8%"],
            )
            self.assertEqual(cursor.fetchone()[0], 1)
            cursor.execute(
                "SELECT COUNT(*) FROM cyberquest_cache WHERE cache_key LIKE %s",
                ["%vc_attempts%"],
            )
            self.assertGreaterEqual(cursor.fetchone()[0], 1)
        for _ in range(4):
            self.assertFalse(check_code(self.user, purpose="login_2fa", submitted_code="000000"))
        record.refresh_from_db()
        self.assertTrue(record.is_used)
        self.assertFalse(check_code(self.user, purpose="login_2fa", submitted_code=record.code))
