from datetime import date
from io import BytesIO
import tempfile
from pathlib import Path

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
