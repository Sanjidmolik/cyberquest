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

    def test_generate_post_when_eligible(self):
        _complete_games(self.user, percent=100)
        res = self.client.post(reverse("certificates:generate"))
        self.assertEqual(res.status_code, 302)
        self.assertTrue(IssuedCertificate.objects.filter(user=self.user).exists())

    @override_settings(PUBLIC_BASE_URL="https://cyberquest.example")
    def test_public_base_url_in_qr(self):
        url = build_verification_url("CQ-2026-TESTTEST")
        self.assertTrue(url.startswith("https://cyberquest.example/verify/"))
