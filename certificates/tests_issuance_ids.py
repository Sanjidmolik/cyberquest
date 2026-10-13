"""Certificate ID uniqueness, re-download versus new issuance, races, and non-Latin names."""

import tempfile
from unittest.mock import patch

import pymupdf
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from certificates.models import IssuedCertificate
from certificates.services import issuance
from certificates.services.generator import generate_certificate_pdf, needs_script_fallback
from certificates.services.issuance import issue_certificate_for_user
from certificates.tests import _TEST_STORAGES, _complete_games

User = get_user_model()


class _MediaTestCase(TestCase):
    def setUp(self):
        self._media = tempfile.TemporaryDirectory()
        self._override = override_settings(MEDIA_ROOT=self._media.name, STORAGES=_TEST_STORAGES)
        self._override.enable()
        self.user = User.objects.create_user(
            email="ids@example.com", password="testpass123", full_name="Ida Example",
        )
        _complete_games(self.user, percent=100)

    def tearDown(self):
        self._override.disable()
        self._media.cleanup()


class CertificateIdTests(_MediaTestCase):
    def test_database_rejects_duplicate_certificate_ids(self):
        cert = issue_certificate_for_user(self.user)
        other = User.objects.create_user(email="dup@example.com", password="testpass123")
        with self.assertRaises(IntegrityError), transaction.atomic():
            IssuedCertificate.objects.create(
                user=other, certificate_id=cert.certificate_id, verification_token="t" * 40,
                recipient_name="Dup", score=90, issued_at=timezone.now(),
            )

    def test_database_rejects_second_certificate_for_same_user(self):
        issue_certificate_for_user(self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            IssuedCertificate.objects.create(
                user=self.user, certificate_id="CQ-2026-000000000000", verification_token="u" * 40,
                recipient_name="Again", score=90, issued_at=timezone.now(),
            )

    def test_id_generator_retries_on_collision(self):
        taken = issue_certificate_for_user(self.user).certificate_id
        with patch.object(issuance, "_make_certificate_id", side_effect=[taken, "CQ-2026-ABCDEF012345"]):
            self.assertEqual(issuance._unique_certificate_id(), "CQ-2026-ABCDEF012345")


class RedownloadTests(_MediaTestCase):
    def test_redownload_serves_same_id_and_bytes_without_xp(self):
        self.client.force_login(self.user)
        xp_before = User.objects.get(pk=self.user.pk).xp
        first = self.client.get(reverse("certificates:download"))
        self.assertEqual(first.status_code, 200)
        first_bytes = b"".join(first.streaming_content)
        cert = IssuedCertificate.objects.get(user=self.user)

        for _ in range(3):
            again = self.client.get(reverse("certificates:download"))
            self.assertEqual(b"".join(again.streaming_content), first_bytes)
        self.client.post(reverse("certificates:generate"))

        self.assertEqual(IssuedCertificate.objects.filter(user=self.user).count(), 1)
        self.assertEqual(IssuedCertificate.objects.get(user=self.user).certificate_id, cert.certificate_id)
        self.assertEqual(User.objects.get(pk=self.user.pk).xp, xp_before)

    def test_staff_regeneration_keeps_the_id(self):
        staff = User.objects.create_user(email="staffcert@example.com", password="x", is_staff=True)
        first = issue_certificate_for_user(staff)
        again = issue_certificate_for_user(staff, force=True)
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(first.certificate_id, again.certificate_id)

    def test_new_issue_after_deletion_gets_a_new_id(self):
        first = issue_certificate_for_user(self.user)
        first.delete()
        second = issue_certificate_for_user(self.user)
        self.assertNotEqual(first.certificate_id, second.certificate_id)


class ConcurrentIssueTests(_MediaTestCase):
    def test_lost_race_returns_the_winner_and_cleans_up(self):
        real_generate = issuance.generate_certificate_pdf
        winner = {}

        def generate_while_another_request_wins(**kwargs):
            pdf = real_generate(**kwargs)
            winner["cert"] = IssuedCertificate.objects.create(
                user=self.user, certificate_id="CQ-2026-AAAAAAAAAAAA", verification_token="w" * 40,
                recipient_name="Ida Example", score=100, issued_at=timezone.now(), pdf_file="issued_certificates/w.pdf",
            )
            return pdf

        with patch.object(issuance, "generate_certificate_pdf", side_effect=generate_while_another_request_wins):
            result = issue_certificate_for_user(self.user)

        self.assertEqual(result.pk, winner["cert"].pk)
        self.assertEqual(IssuedCertificate.objects.filter(user=self.user).count(), 1)
        import os
        leftovers = os.listdir(os.path.join(self._media.name, "issued_certificates"))
        self.assertEqual(leftovers, [], "the losing request's PDF should be deleted")


class NonLatinNameTests(TestCase):
    def test_bengali_name_uses_shaped_fallback_font(self):
        name = "সঞ্জীদ মল্লিক"
        self.assertTrue(needs_script_fallback(name))
        self.assertFalse(needs_script_fallback("Zoë O'Brien-Núñez"))
        pdf = generate_certificate_pdf(
            recipient_name=name, score=90, certificate_id="CQ-2026-ABCDEF012345",
            issued_date_display="13 October 2026", verify_url="https://example.invalid/verify/x/",
        )
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        fonts = " ".join(font[3] for font in doc[0].get_fonts())
        self.assertIn("Noto Sans Bengali", fonts)
        self.assertNotIn("Noto Serif Bengali", fonts)

    def test_long_latin_name_is_drawn(self):
        name = "Maximiliana Alexandrina Theodora Wolfeschlegelsteinhausen-Bergerdorff"
        pdf = generate_certificate_pdf(
            recipient_name=name, score=90, certificate_id="CQ-2026-ABCDEF012345",
            issued_date_display="13 October 2026", verify_url="https://example.invalid/verify/x/",
        )
        text = pymupdf.open(stream=pdf, filetype="pdf")[0].get_text()
        self.assertIn("Wolfeschlegelsteinhausen", text)


@override_settings(STORAGES=_TEST_STORAGES)
class VerificationPrivacyTests(_MediaTestCase):
    def test_verify_page_shows_no_email(self):
        cert = issue_certificate_for_user(self.user)
        page = self.client.get(reverse("certificate_verify", args=[cert.certificate_id]))
        self.assertContains(page, cert.certificate_id)
        self.assertNotContains(page, self.user.email)
