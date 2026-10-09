from datetime import date
from io import BytesIO
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

UserModel = get_user_model()


def _make_image(fmt="JPEG", size=(64, 64), color=(20, 180, 200)):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    buffer.seek(0)
    ext = "jpg" if fmt == "JPEG" else fmt.lower()
    content_type = "image/jpeg" if fmt == "JPEG" else f"image/{ext}"
    return SimpleUploadedFile(f"avatar.{ext}", buffer.read(), content_type=content_type)


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
        self.assertContains(login_page, "Administrator sign in")
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

    def test_signup_lands_on_the_dashboard(self):
        response = self.client.post(reverse("accounts:signup"), {
            "username": "newrecruit",
            "email": "new.recruit@gmail.com",
            "password": "securepass1",
            "confirm_password": "securepass1",
            "date_of_birth": "2000-01-15",
            "cyber_class": "general",
            "skill_level": "beginner",
            "ethical_agreement": "on",
        })
        self.assertRedirects(response, reverse("dashboard:home"))
        self.assertNotEqual(response.url, reverse("courses:intro"))

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
        page = self.client.get(reverse("accounts:admin_login"))
        self.assertContains(page, "Administrator sign in")
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
