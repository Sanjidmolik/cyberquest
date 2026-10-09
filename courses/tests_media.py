import tempfile
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from courses.models import Course

User = get_user_model()
PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _png():
    buffer = BytesIO()
    Image.new("RGB", (12, 12), (20, 40, 80)).save(buffer, format="PNG")
    return buffer.getvalue()


def _body(response):
    payload = b"".join(response.streaming_content)
    response.close()
    return payload


class ProtectedCourseMediaTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)

        self.student = User.objects.create_user(
            email="student.media@gmail.com",
            password="securepass1!",
            username="stumedia",
            ethical_agreement=True,
        )
        self.superuser = User.objects.create_superuser(
            email="super.media@gmail.com",
            password="securepass1!",
        )
        self.client.force_login(self.student)
        self.published = Course.objects.create(
            code="PUB",
            title="Published",
            short_description="Visible",
            content="Text",
            is_published=True,
            pdf_file=ContentFile(PDF_BYTES, name="lesson.pdf"),
            thumbnail=ContentFile(_png(), name="cover.png"),
        )
        self.draft = Course.objects.create(
            code="DRAFT",
            title="Draft",
            short_description="Hidden",
            content="Secret lesson",
            is_published=False,
            pdf_file=ContentFile(PDF_BYTES, name="draft.pdf"),
            thumbnail=ContentFile(_png(), name="draft-cover.png"),
        )

    def test_anonymous_ebook_and_thumbnail_redirect_to_login(self):
        anon = Client()
        ebook = anon.get(reverse("courses:ebook", args=[self.published.code]))
        thumb = anon.get(reverse("courses:thumbnail", args=[self.published.code]))
        self.assertEqual(ebook.status_code, 302)
        self.assertIn("/accounts/login/", ebook.url)
        self.assertEqual(thumb.status_code, 302)

    def test_student_receives_pdf_bytes_for_published_course(self):
        response = self.client.get(reverse("courses:ebook", args=[self.published.code]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(_body(response).startswith(b"%PDF"))
        page = self.client.get(reverse("courses:detail", args=[self.published.code]))
        self.assertContains(page, reverse("courses:ebook", args=[self.published.code]))

    def test_student_thumbnail_for_published_course_only(self):
        ok = self.client.get(reverse("courses:thumbnail", args=[self.published.code]))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok["Content-Type"], "image/png")
        self.assertTrue(_body(ok).startswith(b"\x89PNG"))
        hidden = self.client.get(reverse("courses:thumbnail", args=[self.draft.code]))
        self.assertEqual(hidden.status_code, 404)
        listing = self.client.get(reverse("courses:intro"))
        self.assertContains(listing, reverse("courses:thumbnail", args=[self.published.code]))

    def test_student_unpublished_ebook_is_404_and_superuser_can_open_it(self):
        hidden = self.client.get(reverse("courses:ebook", args=[self.draft.code]))
        self.assertEqual(hidden.status_code, 404)
        self.client.force_login(self.superuser)
        opened = self.client.get(reverse("courses:ebook", args=[self.draft.code]))
        self.assertEqual(opened.status_code, 200)
        self.assertTrue(_body(opened).startswith(b"%PDF"))

    def test_missing_file_is_404(self):
        self.published.pdf_file.name = "course_ebooks/missing.pdf"
        self.published.save(update_fields=["pdf_file"])
        response = self.client.get(reverse("courses:ebook", args=[self.published.code]))
        self.assertEqual(response.status_code, 404)

    def test_path_traversal_is_rejected(self):
        secret = Path(self.media.name).resolve().parent / "media-secret.txt"
        secret.write_text("TOP-SECRET", encoding="utf-8")
        self.addCleanup(secret.unlink, missing_ok=True)
        self.published.pdf_file.name = "../media-secret.txt"
        self.published.save(update_fields=["pdf_file"])
        response = self.client.get(reverse("courses:ebook", args=[self.published.code]))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b"TOP-SECRET", response.content)

        self.published.pdf_file.name = "course_ebooks/../../media-secret.txt"
        self.published.save(update_fields=["pdf_file"])
        nested = self.client.get(reverse("courses:ebook", args=[self.published.code]))
        self.assertEqual(nested.status_code, 404)
        self.assertNotIn(b"TOP-SECRET", nested.content)

    def test_thumbnail_upload_stays_inside_media_root(self):
        from django.conf import settings

        self.published.thumbnail.save("cover.png", ContentFile(_png()), save=True)
        relative = self.published.thumbnail.name.replace("\\", "/")
        self.assertTrue(relative.startswith("course_thumbnails/"))
        full = (Path(settings.MEDIA_ROOT) / self.published.thumbnail.name).resolve()
        self.assertTrue(full.is_relative_to(Path(settings.MEDIA_ROOT).resolve()))
        self.assertTrue(full.is_file())


class SeedPersistentMediaTests(TestCase):
    def test_seed_copies_missing_files_and_does_not_overwrite_or_delete(self):
        from django.conf import settings

        with tempfile.TemporaryDirectory() as dest:
            with override_settings(MEDIA_ROOT=dest):
                call_command("seed_persistent_media")
                handbook = Path(dest) / "course_ebooks" / "The_Phishing_Detectives_Handbook.pdf"
                template = Path(dest) / "certificate_templates" / "a.pdf"
                self.assertTrue(handbook.is_file())
                self.assertTrue(template.is_file())
                handbook.write_bytes(b"KEEP")
                extra = Path(dest) / "course_ebooks" / "admin-upload.pdf"
                extra.write_bytes(b"ADMIN")
                call_command("seed_persistent_media")
                self.assertEqual(handbook.read_bytes(), b"KEEP")
                self.assertEqual(extra.read_bytes(), b"ADMIN")
                self.assertEqual(len(list(Path(settings.MEDIA_ROOT).rglob("*"))), len(list(Path(dest).rglob("*"))))
