from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from games.models import GameAttempt

from certificates.eligibility import (
    MIN_OVERALL_SCORE,
    REQUIRED_GAME_KEYS,
    get_eligibility_status,
    is_eligible_for_certificate,
)
from certificates.models import CertificateTemplate, IssuedCertificate
from certificates.services.generator import generate_certificate_pdf, _fit_textbox
from certificates.services.issuance import (
    CertificateIssuanceError,
    issue_certificate_for_user,
)
from certificates.services.qr import build_verification_url, make_qr_png_bytes

User = get_user_model()

REQUIRED = list(REQUIRED_GAME_KEYS)

# Manifest static storage needs collectstatic; use plain storage in view tests.
_TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def _make_user(email="learner@example.com", **extra):
    return User.objects.create_user(email=email, password="testpass123", **extra)


def _complete_games(user, percent=100):
    """Create one attempt per required game at the given percentage (of 5 questions)."""
    score = round(percent / 100 * 5)
    for key in REQUIRED:
        GameAttempt.objects.create(
            user=user,
            game_key=key,
            score=score,
            total_questions=5,
        )


class EligibilityTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_zero_games_not_eligible(self):
        status = get_eligibility_status(self.user)
        self.assertFalse(is_eligible_for_certificate(self.user))
        self.assertEqual(status["games_completed"], 0)
        self.assertIn("Complete all CyberQuest challenges", status["message"])

    def test_four_of_five_not_eligible(self):
        for key in REQUIRED[:4]:
            GameAttempt.objects.create(user=self.user, game_key=key, score=5, total_questions=5)
        status = get_eligibility_status(self.user)
        self.assertEqual(status["games_completed"], 4)
        self.assertFalse(status["eligible"])
        self.assertIn("Complete all CyberQuest challenges", status["message"])

    def test_five_games_at_79_not_eligible(self):
        # 4/5 = 80% would pass; use 3/5 = 60% for clear fail, then adjust overall.
        # Overall of five games at 79%: score 4/5 = 80 rounds — use mixed scores.
        scores = [4, 4, 4, 4, 3]  # 80,80,80,80,60 → avg 76
        for key, score in zip(REQUIRED, scores):
            GameAttempt.objects.create(user=self.user, game_key=key, score=score, total_questions=5)
        status = get_eligibility_status(self.user)
        self.assertTrue(status["games_requirement_met"])
        self.assertLess(status["overall_score"], MIN_OVERALL_SCORE)
        self.assertFalse(status["eligible"])
        self.assertIn("at least 80%", status["message"])

    def test_five_games_exactly_80_eligible(self):
        _complete_games(self.user, percent=80)
        status = get_eligibility_status(self.user)
        self.assertEqual(status["overall_score"], 80)
        self.assertTrue(status["eligible"])
        self.assertIn("Congratulations", status["message"])

    def test_five_games_at_95_eligible(self):
        _complete_games(self.user, percent=100)
        # Override one to get ~95 average still eligible; all 100 → 100
        status = get_eligibility_status(self.user)
        self.assertGreaterEqual(status["overall_score"], 95)
        self.assertTrue(is_eligible_for_certificate(self.user))

    def test_staff_is_eligible_without_games(self):
        self.user.is_staff = True
        self.user.is_superuser = True
        self.user.save()
        self.assertTrue(is_eligible_for_certificate(self.user))
        status = get_eligibility_status(self.user)
        self.assertTrue(status["eligible"])
        self.assertTrue(status["staff_bypass"])

    def test_staff_can_generate_certificate(self):
        from certificates.services.issuance import issue_certificate_for_user

        admin = _make_user(email="admin-cert@example.com", full_name="Admin User")
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        cert = issue_certificate_for_user(admin)
        self.assertTrue(cert.pdf_file)
        self.assertEqual(cert.score, 100)
        self.assertRegex(cert.certificate_id, r"^CQ-\d{4}-[0-9A-F]{8}$")

    def test_staff_force_regenerates_with_new_template(self):
        from io import BytesIO
        from PIL import Image
        from certificates.services.issuance import issue_certificate_for_user

        admin = _make_user(email="admin-regen@example.com", full_name="Admin Regen")
        admin.is_staff = True
        admin.save()
        first = issue_certificate_for_user(admin)
        self.assertIsNone(first.template_id)

        buf = BytesIO()
        Image.new("RGB", (700, 500), color=(102, 20, 216)).save(buf, format="PNG")
        png = SimpleUploadedFile("new.png", buf.getvalue(), content_type="image/png")
        tmpl = CertificateTemplate.objects.create(name="New Active", pdf_file=png, is_active=True)

        second = issue_certificate_for_user(admin, force=True)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(second.template_id, tmpl.pk)
        self.assertTrue(second.pdf_file.read().startswith(b"%PDF"))


class CertificateIssuanceTests(TestCase):
    def setUp(self):
        self.user = _make_user(full_name="Sanjidur Rahman Sanjid")
        _complete_games(self.user, percent=100)

    def test_certificate_id_unique_format(self):
        cert = issue_certificate_for_user(self.user)
        self.assertRegex(cert.certificate_id, r"^CQ-\d{4}-[0-9A-F]{8}$")
        self.assertEqual(IssuedCertificate.objects.filter(certificate_id=cert.certificate_id).count(), 1)

    def test_generation_creates_pdf(self):
        cert = issue_certificate_for_user(self.user)
        self.assertTrue(cert.pdf_file)
        self.assertGreater(cert.pdf_file.size, 500)
        data = cert.pdf_file.read()
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertEqual(cert.score, 100)
        self.assertEqual(cert.recipient_name, "Sanjidur Rahman Sanjid")

    def test_duplicate_generation_returns_same(self):
        first = issue_certificate_for_user(self.user)
        second = issue_certificate_for_user(self.user)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(IssuedCertificate.objects.filter(user=self.user).count(), 1)

    def test_not_eligible_raises(self):
        other = _make_user(email="other@example.com")
        with self.assertRaises(CertificateIssuanceError):
            issue_certificate_for_user(other)

    def test_score_frozen_after_issue(self):
        cert = issue_certificate_for_user(self.user)
        GameAttempt.objects.filter(user=self.user).update(score=1)
        cert.refresh_from_db()
        self.assertEqual(cert.score, 100)


@override_settings(STORAGES=_TEST_STORAGES)
class QrAndVerifyTests(TestCase):
    def setUp(self):
        self.user = _make_user(full_name="Test User")
        _complete_games(self.user, percent=100)
        self.cert = issue_certificate_for_user(self.user)
        self.client = Client()

    def test_qr_png_bytes(self):
        url = build_verification_url(self.cert.certificate_id)
        png = make_qr_png_bytes(url)
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_verify_valid(self):
        url = reverse("certificate_verify", kwargs={"certificate_id": self.cert.certificate_id})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "CERTIFICATE VERIFIED")
        self.assertContains(res, self.cert.certificate_id)
        self.assertContains(res, "Test User")
        self.assertContains(res, "VALID")

    def test_verify_invalid(self):
        url = reverse("certificate_verify", kwargs={"certificate_id": "CQ-2099-DEADBEEF"})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "INVALID CERTIFICATE")
        self.assertContains(res, "Certificate not found")

    def test_legacy_certificate_verify_path(self):
        url = reverse("certificates:verify", kwargs={"certificate_id": self.cert.certificate_id})
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "CERTIFICATE VERIFIED")


class TemplateUploadTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@example.com", password="adminpass123")
        self.client = Client()
        self.client.login(email="admin@example.com", password="adminpass123")

    def test_pdf_template_upload_validation(self):
        bad = SimpleUploadedFile("notes.txt", b"not a pdf", content_type="text/plain")
        tmpl = CertificateTemplate(name="Bad", pdf_file=bad, is_active=True)
        with self.assertRaises(Exception):
            tmpl.full_clean()

    def test_image_template_upload_accepted(self):
        from io import BytesIO
        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (800, 560), color=(112, 31, 211)).save(buf, format="PNG")
        png = SimpleUploadedFile("design.png", buf.getvalue(), content_type="image/png")
        tmpl = CertificateTemplate(name="PNG design", pdf_file=png, is_active=True)
        tmpl.full_clean()
        tmpl.save()
        self.assertEqual(tmpl.template_kind, "image")

    def test_image_template_generates_pdf(self):
        from io import BytesIO
        from PIL import Image
        from certificates.services.issuance import issue_certificate_for_user

        buf = BytesIO()
        Image.new("RGB", (900, 600), color=(250, 247, 255)).save(buf, format="JPEG")
        jpg = SimpleUploadedFile("bg.jpg", buf.getvalue(), content_type="image/jpeg")
        CertificateTemplate.objects.create(name="JPG bg", pdf_file=jpg, is_active=True)

        user = _make_user(email="img-cert@example.com", full_name="Image Template User")
        user.is_staff = True
        user.save()
        cert = issue_certificate_for_user(user)
        data = cert.pdf_file.read()
        self.assertTrue(data.startswith(b"%PDF"))

    def test_active_template_exclusive(self):
        pdf_a = SimpleUploadedFile("a.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        pdf_b = SimpleUploadedFile("b.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        a = CertificateTemplate.objects.create(name="A", pdf_file=pdf_a, is_active=True)
        b = CertificateTemplate.objects.create(name="B", pdf_file=pdf_b, is_active=True)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertFalse(a.is_active)
        self.assertTrue(b.is_active)


class GeneratorUnitTests(TestCase):
    def test_default_pdf_generation(self):
        pdf = generate_certificate_pdf(
            recipient_name="Abdur Rahman Ibn Mohammad",
            score=87,
            certificate_id="CQ-2026-8F4A92D1",
            issued_date_display="07 October 2026",
            verify_url="https://example.com/verify/CQ-2026-8F4A92D1/",
        )
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)
        import pymupdf
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        text = doc[0].get_text()
        self.assertIn("Abdur Rahman Ibn Mohammad", text)
        self.assertIn("87%", text)
        self.assertIn("CQ-2026-8F4A92D1", text)
        self.assertIn("07 October 2026", text)
        blocks = []
        for block in doc[0].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                content = "".join(span["text"] for span in line["spans"])
                blocks.append((content, line["bbox"]))
        doc.close()
        sentence = next(box for content, box in blocks if "proudly presented" in content)
        name = next(box for content, box in blocks if content == "Abdur Rahman Ibn Mohammad")
        self.assertGreater(name[1], sentence[3] + 8)
        self.assertLess(name[3], 308)

    def test_preview_omits_unissued_identity(self):
        import pymupdf
        pdf = generate_certificate_pdf(
            recipient_name="Preview Learner",
            score=42,
            certificate_id="",
            issued_date_display="",
            verify_url="",
        )
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        text = doc[0].get_text()
        doc.close()
        self.assertIn("Preview Learner", text)
        self.assertIn("42%", text)
        self.assertNotIn("CQ-", text)

    def test_long_name_fitting(self):
        import pymupdf

        doc = pymupdf.open()
        page = doc.new_page(width=500, height=200)
        rect = pymupdf.Rect(40, 40, 460, 100)
        size = _fit_textbox(
            page,
            rect,
            "Md. Abdullah Al Mamun Abdur Rahman",
            "helv",
            max_size=40,
            min_size=10,
        )
        self.assertLessEqual(size, 40)
        self.assertGreaterEqual(size, 10)
        doc.close()


@override_settings(STORAGES=_TEST_STORAGES)
class CertificatePageViewTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client = Client()
        self.client.login(email="learner@example.com", password="testpass123")

    def test_page_locked_message(self):
        res = self.client.get(reverse("certificates:page"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Complete all CyberQuest challenges")
        self.assertContains(res, reverse("certificates:preview"))

    def test_preview_is_png(self):
        res = self.client.get(reverse("certificates:preview"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "image/png")
        self.assertTrue(res.content.startswith(b"\x89PNG"))

    def test_generate_post_when_eligible(self):
        _complete_games(self.user, percent=100)
        res = self.client.post(reverse("certificates:generate"))
        self.assertEqual(res.status_code, 302)
        self.assertTrue(IssuedCertificate.objects.filter(user=self.user).exists())

    @override_settings(PUBLIC_BASE_URL="https://cyberquest.example")
    def test_public_base_url_in_qr(self):
        url = build_verification_url("CQ-2026-TESTTEST")
        self.assertTrue(url.startswith("https://cyberquest.example/verify/"))


class ProtectedCertificateFileTests(TestCase):
    def test_download_stays_with_the_owner_and_templates_are_superuser_only(self):
        import tempfile
        from io import BytesIO

        from django.core.files.base import ContentFile
        from PIL import Image

        from certificates.models import Signatory

        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                owner = _make_user(email="owner.cert@example.com", full_name="Owner Cert")
                owner.is_staff = True
                owner.is_superuser = True
                owner.save()
                cert = issue_certificate_for_user(owner)
                self.assertTrue(cert.pdf_file.name.replace("\\", "/").startswith("issued_certificates/"))
                owner_client = Client()
                owner_client.force_login(owner)
                downloaded = owner_client.get(reverse("certificates:download"))
                self.assertEqual(downloaded.status_code, 200)
                self.assertEqual(downloaded["Content-Type"], "application/pdf")
                self.assertTrue(b"".join(downloaded.streaming_content).startswith(b"%PDF"))
                downloaded.close()

                other = _make_user(email="other.cert@example.com")
                other_client = Client()
                other_client.force_login(other)
                denied = other_client.get(reverse("certificates:download"))
                self.assertNotEqual(denied.get("Content-Type"), "application/pdf")

                buffer = BytesIO()
                Image.new("RGB", (40, 20), (255, 255, 255)).save(buffer, format="PNG")
                template = CertificateTemplate.objects.create(
                    name="Preview",
                    pdf_file=ContentFile(buffer.getvalue(), name="design.png"),
                    is_active=False,
                )
                generated = generate_certificate_pdf(
                    recipient_name="Owner Cert",
                    score=80,
                    certificate_id="CQ-2026-TESTFILE",
                    issued_date_display="9 Oct 2026",
                    verify_url="https://example.test/verify/CQ-2026-TESTFILE",
                    template=template,
                    require_template=True,
                )
                self.assertTrue(generated.startswith(b"%PDF"))
                signatory = Signatory.objects.create(
                    name="Ada",
                    title="Director",
                    signature_image=ContentFile(buffer.getvalue(), name="sign.png"),
                )
                student_template = other_client.get(reverse("certificates:template_file", args=[template.pk]))
                student_signature = other_client.get(reverse("certificates:signature_file", args=[signatory.pk]))
                self.assertEqual(student_template.status_code, 404)
                self.assertEqual(student_signature.status_code, 404)
                owner_template = owner_client.get(reverse("certificates:template_file", args=[template.pk]))
                owner_signature = owner_client.get(reverse("certificates:signature_file", args=[signatory.pk]))
                self.assertEqual(owner_template.status_code, 200)
                self.assertEqual(owner_signature.status_code, 200)
                self.assertTrue(b"".join(owner_template.streaming_content).startswith(b"\x89PNG"))
                owner_template.close()
                owner_signature.close()

                student_issued = other_client.get(reverse("certificates:issued_file", args=[cert.pk]))
                self.assertEqual(student_issued.status_code, 404)
                admin_issued = owner_client.get(reverse("certificates:issued_file", args=[cert.pk]))
                self.assertEqual(admin_issued.status_code, 200)
                self.assertEqual(admin_issued["Content-Type"], "application/pdf")
                self.assertTrue(b"".join(admin_issued.streaming_content).startswith(b"%PDF"))
                admin_issued.close()

                change = owner_client.get(
                    reverse("admin:certificates_issuedcertificate_change", args=[cert.pk])
                )
                self.assertEqual(change.status_code, 200)
                issued_url = reverse("certificates:issued_file", args=[cert.pk])
                self.assertContains(change, issued_url)
                self.assertNotContains(change, "/media/")


class TemplateManagementTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            email="template.root@gmail.com", password="pass12345", username="templateroot",
        )
        self.student = _make_user(email="template.student@gmail.com", username="templatestudent")
        self.client.force_login(self.superuser)

    def _png(self, name="design.png"):
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", (900, 600), color=(40, 16, 80)).save(buf, format="PNG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")

    def test_student_cannot_manage_templates(self):
        self.client.force_login(self.student)
        listing = self.client.get(reverse("ops:certificate_templates"))
        self.assertEqual(listing.status_code, 403)
        created = self.client.post(reverse("ops:certificate_template_new"), {"name": "Nope"})
        self.assertEqual(created.status_code, 403)

    def test_upload_activation_and_sample_preview_do_not_issue(self):
        before = IssuedCertificate.objects.count()
        response = self.client.post(reverse("ops:certificate_template_new"), {
            "name": "Image design",
            "pdf_file": self._png(),
            "is_active": "on",
            "field_config": "{}",
        })
        template = CertificateTemplate.objects.get(name="Image design")
        self.assertRedirects(response, reverse("ops:certificate_template_edit", args=[template.pk]))
        self.assertTrue(template.is_active)
        self.assertEqual(CertificateTemplate.objects.filter(is_active=True).count(), 1)
        preview = self.client.get(reverse("ops:certificate_template_preview", args=[template.pk]))
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview["Content-Type"], "image/png")
        self.assertTrue(preview.content.startswith(b"\x89PNG"))
        self.assertEqual(IssuedCertificate.objects.count(), before)
        page = self.client.get(reverse("ops:certificate_template_edit", args=[template.pk]))
        self.assertContains(page, "Sample preview")
        self.assertContains(page, "SAMPLE-ONLY")
        self.assertContains(page, "Visual builder")
        self.assertNotContains(page, "<textarea")
        self.assertContains(page, 'type="hidden" name="field_config"')

    def test_malformed_coordinates_and_bad_upload_are_rejected(self):
        bad_json = self.client.post(reverse("ops:certificate_template_new"), {
            "name": "Broken",
            "pdf_file": self._png("ok.png"),
            "field_config": "{",
        })
        self.assertEqual(bad_json.status_code, 200)
        self.assertContains(bad_json, "valid JSON")
        self.assertFalse(CertificateTemplate.objects.filter(name="Broken").exists())
        bad_file = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        bad_upload = self.client.post(reverse("ops:certificate_template_new"), {
            "name": "Wrong file",
            "pdf_file": bad_file,
            "field_config": "{}",
        })
        self.assertEqual(bad_upload.status_code, 200)
        self.assertFalse(CertificateTemplate.objects.filter(name="Wrong file").exists())

    def test_saved_coordinates_move_the_name(self):
        import pymupdf
        from certificates.services.generator import generate_certificate_pdf
        template = CertificateTemplate.objects.create(
            name="Positioned",
            pdf_file=self._png("placed.png"),
            is_active=True,
            field_config={
                "name": {"x": 40, "y": 50, "w": 400, "h": 40, "fontsize": 18, "align": 0, "color": "#FFFFFF"},
            },
        )
        pdf = generate_certificate_pdf(
            recipient_name="Placed Learner",
            score=85,
            certificate_id="CQ-2026-ABCDEF01",
            issued_date_display="09 October 2026",
            verify_url="https://example.com/verify/CQ-2026-ABCDEF01/",
            template=template,
            require_template=True,
        )
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        name = None
        for block in doc[0].get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                content = "".join(span["text"] for span in line["spans"])
                if content == "Placed Learner":
                    name = line["bbox"]
        doc.close()
        self.assertIsNotNone(name)
        self.assertLess(name[1], 80)
        self.assertGreater(name[1], 40)

    def test_placeholder_is_not_drawn_twice(self):
        import pymupdf
        from certificates.services.generator import generate_certificate_pdf
        doc = pymupdf.open()
        page = doc.new_page(width=842, height=595)
        page.insert_text(pymupdf.Point(80, 120), "{{NAME}}", fontsize=18)
        raw = doc.tobytes()
        doc.close()
        uploaded = SimpleUploadedFile("holders.pdf", raw, content_type="application/pdf")
        template = CertificateTemplate.objects.create(
            name="Holders",
            pdf_file=uploaded,
            is_active=True,
            field_config={"name": {"x": 400, "y": 400, "w": 200, "h": 40, "fontsize": 18}},
        )
        pdf = generate_certificate_pdf(
            recipient_name="Once Only",
            score=85,
            certificate_id="CQ-2026-ABCDEF02",
            issued_date_display="09 October 2026",
            verify_url="https://example.com/verify/CQ-2026-ABCDEF02/",
            template=template,
            require_template=True,
        )
        opened = pymupdf.open(stream=pdf, filetype="pdf")
        self.assertEqual(opened[0].get_text().count("Once Only"), 1)
        opened.close()

    def test_outside_coordinates_block_activation(self):
        template = CertificateTemplate.objects.create(
            name="Outside",
            pdf_file=self._png("outside.png"),
            field_config={"name": {"x": 5000, "y": 10, "w": 100, "h": 20, "fontsize": 12}},
        )
        response = self.client.post(reverse("ops:certificate_template_activate", args=[template.pk]))
        self.assertEqual(response.status_code, 302)
        template.refresh_from_db()
        self.assertFalse(template.is_active)

    def test_display_pixels_convert_to_page_points(self):
        from certificates.layout import display_to_page
        self.assertEqual(display_to_page(200, 400, 842), 421.0)
        self.assertEqual(display_to_page(100, 400, 842), display_to_page(50, 200, 842))

    def test_visual_positions_save_and_reload(self):
        import json
        template = CertificateTemplate.objects.create(name="Reload", pdf_file=self._png("reload.png"))
        payload = {
            "name": {"x": 30, "y": 70, "w": 220, "h": 36, "fontsize": 16, "align": 1, "color": "#FFFFFF"},
            "score": {"x": 30, "y": 120, "w": 80, "h": 24, "fontsize": 14, "align": 1, "color": "#FFFFFF"},
            "date": {"x": 30, "y": 180, "w": 160, "h": 20, "fontsize": 10, "align": 0, "color": "#FFFFFF"},
            "certificate_id": {"x": 30, "y": 210, "w": 180, "h": 20, "fontsize": 10, "align": 0, "color": "#FFFFFF"},
            "qr": {"x": 320, "y": 180, "size": 48},
        }
        saved = self.client.post(reverse("ops:certificate_template_edit", args=[template.pk]), {
            "name": "Reload",
            "is_active": "",
            "field_config": json.dumps(payload),
            "continue": "1",
        })
        self.assertRedirects(saved, reverse("ops:certificate_template_edit", args=[template.pk]))
        template.refresh_from_db()
        self.assertEqual(template.field_config["name"]["y"], 70)
        page = self.client.get(reverse("ops:certificate_template_edit", args=[template.pk]))
        self.assertContains(page, '"y": 70')
        turned_off = self.client.post(reverse("ops:certificate_template_activate", args=[template.pk]))
        self.assertRedirects(turned_off, reverse("ops:certificate_templates"))
        template.refresh_from_db()
        self.assertTrue(template.is_active)
        off = self.client.post(reverse("ops:certificate_template_deactivate", args=[template.pk]))
        self.assertRedirects(off, reverse("ops:certificate_templates"))
        template.refresh_from_db()
        self.assertFalse(template.is_active)

    def test_changing_the_template_leaves_issued_pdfs_unchanged(self):
        from certificates.services.issuance import issue_certificate_for_user
        admin = _make_user(email="issued.keep@gmail.com", username="issuedkeep", full_name="Issued Keep")
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        cert = issue_certificate_for_user(admin)
        original = cert.pdf_file.read()
        CertificateTemplate.objects.create(
            name="Later design",
            pdf_file=self._png("later.png"),
            is_active=True,
            field_config={"name": {"x": 12, "y": 12, "w": 200, "h": 30, "fontsize": 14}},
        )
        cert.refresh_from_db()
        cert.pdf_file.open("rb")
        self.assertEqual(cert.pdf_file.read(), original)
        self.assertEqual(IssuedCertificate.objects.filter(certificate_id="SAMPLE-ONLY").count(), 0)
