"""
Phase 1 — Step 10: storage adapter, private file access, upload validation,
missing files, and local-storage compatibility.

No test talks to Cloudflare. The R2 adapter is exercised with botocore's
Stubber, and every app code path is run against MemoryRemoteStorage, an
in-memory storage that, like R2, has no local filesystem paths.
"""

import io
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pymupdf
from botocore.stub import ANY, Stubber
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from certificates.models import CertificateTemplate, IssuedCertificate, Signatory
from courses.models import EBOOK_MAX_BYTES, Course, validate_course_ebook
from cyberquest import media_access
from cyberquest.storage import PrivateR2Storage
from cyberquest.storage_config import default_storage_setting
from games.models import GameAttempt

User = get_user_model()
FAKE_BUCKET_HOST = "bucket.invalid"


class MemoryRemoteStorage(Storage):
    """Remote-like storage: bytes in a dict, no path(), signed-looking URLs."""

    files: dict = {}
    opened: list = []

    def _save(self, name, content):
        content.seek(0)
        self.files[name] = content.read()
        return name

    def _open(self, name, mode="rb"):
        if name not in self.files:
            raise FileNotFoundError(name)
        self.opened.append(name)
        return ContentFile(self.files[name], name=name)

    def exists(self, name):
        return name in self.files

    def delete(self, name):
        self.files.pop(name, None)

    def size(self, name):
        return len(self.files[name])

    def url(self, name):
        return f"https://{FAKE_BUCKET_HOST}/{name}?X-Amz-Signature=fake"


REMOTE_STORAGES = {
    "default": {"BACKEND": "cyberquest.tests_storage.MemoryRemoteStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def _png_bytes(size=(900, 600), color=(40, 16, 80)):
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


def _pdf_bytes(pages=3):
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def _complete_games(user):
    from certificates.eligibility import REQUIRED_GAME_KEYS

    for key in REQUIRED_GAME_KEYS:
        GameAttempt.objects.create(user=user, game_key=key, score=5, total_questions=5)


class RemoteStorageTestCase(TestCase):
    def setUp(self):
        MemoryRemoteStorage.files = {}
        MemoryRemoteStorage.opened = []
        cache.clear()
        self._override = override_settings(STORAGES=REMOTE_STORAGES)
        self._override.enable()

    def tearDown(self):
        self._override.disable()


# ---------------------------------------------------------------- Steps 2–4
class StorageConfigTests(TestCase):
    def test_filesystem_is_the_default(self):
        self.assertEqual(default_storage_setting({})["BACKEND"], "django.core.files.storage.FileSystemStorage")
        from django.core.files.storage import storages
        self.assertIsInstance(storages["default"], FileSystemStorage)

    def test_r2_requires_every_credential_and_never_echoes_values(self):
        env = {"MEDIA_STORAGE": "r2", "R2_ACCESS_KEY_ID": "AKIA-SHOULD-NOT-APPEAR", "R2_BUCKET_NAME": "b"}
        with self.assertRaises(ImproperlyConfigured) as caught:
            default_storage_setting(env)
        message = str(caught.exception)
        self.assertIn("R2_SECRET_ACCESS_KEY", message)
        self.assertIn("R2_ENDPOINT_URL or R2_ACCOUNT_ID", message)
        self.assertNotIn("AKIA-SHOULD-NOT-APPEAR", message)

    def test_r2_setting_from_account_id(self):
        setting = default_storage_setting({
            "MEDIA_STORAGE": "r2", "R2_ACCESS_KEY_ID": "id", "R2_SECRET_ACCESS_KEY": "secret",
            "R2_BUCKET_NAME": "cq-media", "R2_ACCOUNT_ID": "abc123", "R2_SIGNED_URL_SECONDS": "99999",
        })
        self.assertEqual(setting["BACKEND"], "cyberquest.storage.PrivateR2Storage")
        options = setting["OPTIONS"]
        self.assertEqual(options["endpoint_url"], "https://abc123.r2.cloudflarestorage.com")
        self.assertEqual(options["region_name"], "auto")
        self.assertEqual(options["location"], "media")
        self.assertEqual(options["querystring_expire"], 300)  # out of range falls back

    def test_r2_endpoint_must_be_https(self):
        with self.assertRaises(ImproperlyConfigured):
            default_storage_setting({
                "MEDIA_STORAGE": "r2", "R2_ACCESS_KEY_ID": "i", "R2_SECRET_ACCESS_KEY": "s",
                "R2_BUCKET_NAME": "b", "R2_ENDPOINT_URL": "http://insecure.example",
            })

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            default_storage_setting({"MEDIA_STORAGE": "s3-public"})


def _r2_storage(**overrides):
    options = dict(
        bucket_name="cq-test", endpoint_url="https://acct.r2.cloudflarestorage.com",
        access_key="AKIDEXAMPLE", secret_key="SECRETEXAMPLE", location="media",
    )
    options.update(overrides)
    return PrivateR2Storage(**options)


class PrivateR2StorageTests(TestCase):
    def test_privacy_options_cannot_be_loosened(self):
        storage = _r2_storage(default_acl="public-read", querystring_auth=False, file_overwrite=True,
                              custom_domain="cdn.example.com")
        self.assertIsNone(storage.default_acl)
        self.assertTrue(storage.querystring_auth)
        self.assertFalse(storage.file_overwrite)
        self.assertIsNone(storage.custom_domain)

    def test_url_is_short_lived_and_signed(self):
        url = _r2_storage().url("issued_certificates/CQ-1.pdf")
        self.assertTrue(url.startswith("https://acct.r2.cloudflarestorage.com/"))
        self.assertIn("X-Amz-Signature=", url)
        self.assertIn("X-Amz-Expires=300", url)

    def test_save_exists_open_and_missing_object_with_stubbed_r2(self):
        storage = _r2_storage()
        client = storage.connection.meta.client
        key = "media/issued_certificates/CQ-1.pdf"
        body = b"%PDF-1.4 certificate"
        with Stubber(client) as stub:
            stub.add_client_error("head_object", http_status_code=404, service_error_code="404",
                                  expected_params={"Bucket": "cq-test", "Key": key})
            # No ACL parameter: the bucket's private policy applies.
            stub.add_response("put_object", {}, {"Bucket": "cq-test", "Key": key, "Body": ANY,
                                                 "ContentType": "application/pdf"})
            name = storage.save("issued_certificates/CQ-1.pdf", ContentFile(body))
            self.assertEqual(name, "issued_certificates/CQ-1.pdf")
            stub.add_response("head_object", {"ContentLength": len(body)}, {"Bucket": "cq-test", "Key": key})
            self.assertTrue(storage.exists(name))
            stub.add_response("head_object", {"ContentLength": len(body)}, {"Bucket": "cq-test", "Key": key})
            stub.add_response("get_object", {"Body": io.BytesIO(body), "ContentLength": len(body)},
                              {"Bucket": "cq-test", "Key": key, "Range": ANY})
            with storage.open(name, "rb") as handle:
                self.assertEqual(handle.read(), body)
            stub.add_client_error("head_object", http_status_code=404, service_error_code="404",
                                  expected_params={"Bucket": "cq-test", "Key": "media/gone.pdf"})
            self.assertFalse(storage.exists("gone.pdf"))
            stub.assert_no_pending_responses()

    def test_no_local_path(self):
        with self.assertRaises(NotImplementedError):
            _r2_storage().path("x.pdf")


# ---------------------------------------------------------------- Step 5–6
class MediaAccessTests(RemoteStorageTestCase):
    def test_unsafe_names_are_refused(self):
        user = User.objects.create_user(email="u@example.com", password="x")
        MemoryRemoteStorage.files["../secret.txt"] = b"nope"
        user.profile_picture.name = "../secret.txt"
        self.assertIsNone(media_access.serve_stored_file(user.profile_picture))
        self.assertIsNone(media_access.open_stored_file(user.profile_picture))

    def test_local_copy_removes_its_temporary_file(self):
        user = User.objects.create_user(email="t@example.com", password="x")
        user.profile_picture.save("p.png", ContentFile(_png_bytes((10, 10))), save=True)
        with media_access.local_copy(user.profile_picture) as path:
            self.assertTrue(Path(path).is_file())
            kept = Path(path)
        self.assertFalse(kept.exists())

    def test_missing_remote_file_is_none_not_an_error(self):
        user = User.objects.create_user(email="m@example.com", password="x")
        user.profile_picture.name = "profile_pictures/missing.png"
        self.assertIsNone(media_access.serve_stored_file(user.profile_picture))
        self.assertFalse(media_access.file_exists(user.profile_picture))
        with media_access.local_copy(user.profile_picture) as path:
            self.assertIsNone(path)


class ProfilePhotoAccessTests(RemoteStorageTestCase):
    def test_photo_is_served_privately_through_the_view(self):
        owner = User.objects.create_user(email="owner@example.com", password="x", username="owner")
        owner.profile_picture.save("face.png", ContentFile(_png_bytes((20, 20))), save=True)
        url = reverse("accounts:profile_photo", args=[owner.pk])
        self.assertEqual(self.client.get(url).status_code, 302)  # anonymous
        viewer = User.objects.create_user(email="viewer@example.com", password="x", username="viewer")
        self.client.force_login(viewer)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), MemoryRemoteStorage.files[owner.profile_picture.name])
        self.assertEqual(response["Cache-Control"], "private, max-age=300")


class CertificateRemoteStorageTests(RemoteStorageTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(email="learner@example.com", password="x", full_name="সঞ্জীদ মল্লিক")
        _complete_games(self.user)

    def test_issue_download_preview_redownload_and_no_xp(self):
        self.client.force_login(self.user)
        xp_before = User.objects.get(pk=self.user.pk).xp
        first = self.client.get(reverse("certificates:download"))
        self.assertEqual(first.status_code, 200)
        first_bytes = b"".join(first.streaming_content)
        cert = IssuedCertificate.objects.get(user=self.user)
        self.assertEqual(MemoryRemoteStorage.files[cert.pdf_file.name], first_bytes)
        again = self.client.get(reverse("certificates:download"))
        self.assertEqual(b"".join(again.streaming_content), first_bytes)
        preview = self.client.get(reverse("certificates:preview"))
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview["Content-Type"], "image/png")
        self.assertEqual(IssuedCertificate.objects.get(user=self.user).certificate_id, cert.certificate_id)
        self.assertEqual(User.objects.get(pk=self.user.pk).xp, xp_before)
        # Bengali name rendered with the bundled shaping font.
        fonts = " ".join(f[3] for f in pymupdf.open(stream=first_bytes, filetype="pdf")[0].get_fonts())
        self.assertIn("Noto Sans Bengali", fonts)

    def test_missing_issued_pdf_is_never_rebuilt_silently(self):
        from certificates.services.issuance import issue_certificate_for_user

        cert = issue_certificate_for_user(self.user)
        name = cert.pdf_file.name
        del MemoryRemoteStorage.files[name]
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("certificates:download")).status_code, 404)
        self.assertEqual(self.client.get(reverse("certificates:preview")).status_code, 404)
        self.assertEqual(self.client.get(reverse("certificates:view")).status_code, 404)
        cert.refresh_from_db()
        self.assertEqual(cert.pdf_file.name, name)
        self.assertNotIn(name, MemoryRemoteStorage.files)

    def test_qr_points_at_public_verification_page(self):
        from certificates.services import generator

        captured = {}
        real = generator.make_qr_png_bytes

        def spy(url):
            captured["url"] = url
            return real(url)

        with override_settings(PUBLIC_BASE_URL="https://cyberquest.example"), \
                patch.object(generator, "make_qr_png_bytes", side_effect=spy):
            from certificates.services.issuance import issue_certificate_for_user
            cert = issue_certificate_for_user(self.user)
        self.assertEqual(captured["url"], f"https://cyberquest.example/verify/{cert.certificate_id}/")
        self.assertContains(self.client.get(reverse("certificate_verify", args=[cert.certificate_id])), "VERIFIED")

    def test_owner_only_download(self):
        from certificates.services.issuance import issue_certificate_for_user

        cert = issue_certificate_for_user(self.user)
        other = User.objects.create_user(email="other@example.com", password="x")
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse("certificates:issued_file", args=[cert.pk])).status_code, 404)


class TemplateRemoteStorageTests(RemoteStorageTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(email="root@example.com", password="x")
        self.client.force_login(self.admin)

    def test_uploaded_template_renders_previews_and_editor_from_remote_storage(self):
        template = CertificateTemplate.objects.create(
            name="Remote design",
            pdf_file=SimpleUploadedFile("design.png", _png_bytes(), content_type="image/png"),
            field_config={"name": {"x": 100, "y": 200, "w": 600, "h": 50, "fontsize": 30}},
        )
        self.assertIn(template.pdf_file.name, MemoryRemoteStorage.files)
        artwork = self.client.get(reverse("ops:certificate_template_artwork", args=[template.pk]))
        self.assertEqual(artwork.status_code, 200)
        preview = self.client.get(reverse("ops:certificate_template_preview", args=[template.pk]))
        self.assertEqual(preview.status_code, 200)
        editor = self.client.get(reverse("ops:certificate_template_edit", args=[template.pk]))
        self.assertEqual(editor.status_code, 200)
        self.assertNotContains(editor, FAKE_BUCKET_HOST)
        # Visual placement survives a save and reload.
        template.field_config = {"name": {"x": 120, "y": 210, "w": 600, "h": 50, "fontsize": 28}}
        template.save()
        template.refresh_from_db()
        self.assertEqual(template.field_config["name"]["x"], 120)

    def test_builtin_design_uses_its_own_renderer_even_if_not_in_the_bucket(self):
        from certificates.services import generator

        template = CertificateTemplate.objects.create(name="Built-in", is_active=True)
        template.pdf_file.name = "certificate_templates/" + generator.ACHIEVEMENT_TEMPLATE_NAME
        template.save()
        self.assertNotIn(template.pdf_file.name, MemoryRemoteStorage.files)
        with patch.object(generator, "_fill_achievement_template", wraps=generator._fill_achievement_template) as spy:
            pdf = generator.generate_certificate_pdf(
                recipient_name="Ana Li", score=90, certificate_id="CQ-2026-ABCDEF012345",
                issued_date_display="13 October 2026", verify_url="https://x.example/verify/a/",
                template=template, require_template=True,
            )
        self.assertTrue(spy.called)
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_signature_upload_and_superuser_only_file_view(self):
        signatory = Signatory.objects.create(
            name="Signer", title="Director",
            signature_image=SimpleUploadedFile("sig.png", _png_bytes((60, 20)), content_type="image/png"),
        )
        self.assertIn(signatory.signature_image.name, MemoryRemoteStorage.files)
        url = reverse("certificates:signature_file", args=[signatory.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        student = User.objects.create_user(email="s@example.com", password="x")
        self.client.force_login(student)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_admin_pages_link_protected_views_not_bucket_urls(self):
        course = Course.objects.create(code="MOD-R2", title="Remote", short_description="s")
        course.pdf_file.save("guide.pdf", ContentFile(_pdf_bytes()), save=False)
        course.thumbnail.save("cover.png", ContentFile(_png_bytes((40, 40))), save=True)
        self.admin.profile_picture.save("me.png", ContentFile(_png_bytes((20, 20))), save=True)
        pages = [
            reverse("admin:courses_course_change", args=[course.pk]),
            reverse("admin:accounts_customuser_change", args=[self.admin.pk]),
        ]
        for page in pages:
            response = self.client.get(page)
            self.assertEqual(response.status_code, 200, page)
            self.assertNotContains(response, FAKE_BUCKET_HOST)
        self.assertContains(self.client.get(pages[0]), reverse("courses:ebook", args=["MOD-R2"]))
        self.assertContains(self.client.get(pages[1]), reverse("accounts:profile_photo", args=[self.admin.pk]))


class CourseRemoteStorageTests(RemoteStorageTestCase):
    def test_ebook_served_and_page_count_cached(self):
        from courses.progress import server_total_pages

        course = Course.objects.create(code="MOD-PG", title="Pages", short_description="s", is_published=True)
        course.pdf_file.save("book.pdf", ContentFile(_pdf_bytes(pages=4)), save=True)
        MemoryRemoteStorage.opened = []
        self.assertEqual(server_total_pages(course), 5)
        self.assertEqual(server_total_pages(course), 5)
        self.assertEqual(MemoryRemoteStorage.opened.count(course.pdf_file.name), 1)
        learner = User.objects.create_user(email="reader@example.com", password="x")
        self.client.force_login(learner)
        response = self.client.get(reverse("courses:ebook", args=["MOD-PG"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_thumbnail_existence_check_is_cached(self):
        course = Course.objects.create(code="MOD-TH", title="Thumb", short_description="s")
        course.thumbnail.save("t.png", ContentFile(_png_bytes((30, 30))), save=True)
        self.assertTrue(course.safe_thumbnail_url())
        del MemoryRemoteStorage.files[course.thumbnail.name]
        self.assertTrue(course.safe_thumbnail_url())  # cached for 10 minutes
        cache.clear()
        self.assertEqual(course.safe_thumbnail_url(), "")


class PrivacyRemoteStorageTests(RemoteStorageTestCase):
    def test_export_includes_picture_and_deletion_removes_remote_files(self):
        user = User.objects.create_user(email="leaver@example.com", password="securepass1!", username="leaver")
        user.profile_picture.save("p.png", ContentFile(_png_bytes((12, 12))), save=True)
        name = user.profile_picture.name
        self.client.force_login(user)
        export = self.client.post(reverse("accounts:data_export"), {"format": "csv"})
        import zipfile
        self.assertIn("profile_picture.png", zipfile.ZipFile(io.BytesIO(export.content)).namelist())
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("accounts:delete_account"), {"password": "securepass1!", "confirm": "DELETE"})
        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        self.assertNotIn(name, MemoryRemoteStorage.files)


# ---------------------------------------------------------------- Step 7
class EbookUploadLimitTests(TestCase):
    def _pdf_upload(self, size):
        upload = SimpleUploadedFile("book.pdf", b"%PDF-1.4\n", content_type="application/pdf")
        upload.size = size
        return upload

    def test_model_validator_boundary(self):
        validate_course_ebook(self._pdf_upload(EBOOK_MAX_BYTES))
        with self.assertRaises(ValidationError):
            validate_course_ebook(self._pdf_upload(EBOOK_MAX_BYTES + 1))

    def test_already_stored_ebook_is_not_revalidated(self):
        from django.db.models.fields.files import FieldFile

        course = Course(code="MOD-OLD", title="Old", short_description="s")
        stored = FieldFile(course, Course._meta.get_field("pdf_file"), "course_ebooks/old.pdf")
        stored._committed = True
        with patch.object(FieldFile, "size", new=EBOOK_MAX_BYTES * 2):
            validate_course_ebook(stored)  # no error: existing files keep working

    def test_command_center_form_boundary(self):
        from dashboard.ops_forms import CourseManageForm

        data = {"code": "MOD-SZ", "title": "Size", "short_description": "s", "content": "", "order": "1"}
        ok = CourseManageForm(data, {"pdf_file": self._pdf_upload(EBOOK_MAX_BYTES)})
        self.assertTrue(ok.is_valid(), ok.errors)
        too_big = CourseManageForm(data, {"pdf_file": self._pdf_upload(EBOOK_MAX_BYTES + 1)})
        self.assertFalse(too_big.is_valid())
        self.assertIn("25 MB", str(too_big.errors["pdf_file"]))

    def test_oversized_upload_is_rejected_end_to_end(self):
        admin = User.objects.create_superuser(email="root2@example.com", password="x")
        self.client.force_login(admin)
        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            big = SimpleUploadedFile("big.pdf", b"%PDF-1.4\n" + b"0" * EBOOK_MAX_BYTES,
                                     content_type="application/pdf")
            response = self.client.post(reverse("admin:courses_course_add"), {
                "code": "MOD-BIG", "title": "Big", "short_description": "s", "order": "1",
                "is_published": "on", "content": "", "pdf_file": big,
            })
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "25 MB")
            self.assertFalse(Course.objects.filter(code="MOD-BIG").exists())
            self.assertEqual(os.listdir(media), [])


# ---------------------------------------------------------------- Step 4 (local)
class LocalStorageCompatibilityTests(TestCase):
    def test_local_files_still_served_and_contained(self):
        with tempfile.TemporaryDirectory() as media, self.settings(MEDIA_ROOT=media):
            user = User.objects.create_user(email="local@example.com", password="x")
            user.profile_picture.save("local.png", ContentFile(_png_bytes((8, 8))), save=True)
            self.assertTrue(media_access.is_local(user.profile_picture))
            path = media_access.stored_file_path(user.profile_picture)
            self.assertTrue(str(path).startswith(str(Path(media).resolve())))
            with media_access.local_copy(user.profile_picture) as same:
                self.assertEqual(same, path)  # no temporary copy for local files
            self.assertTrue(path.exists())
            response = media_access.serve_stored_file(user.profile_picture)
            self.assertEqual(b"".join(response.streaming_content), path.read_bytes())
            response.close()
