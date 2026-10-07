"""
certificates/services/issuance.py
---------------------------------
Issue a certificate once per user with row-level locking to prevent duplicates.
Staff may force-regenerate so a newly uploaded admin template is applied.
"""

from __future__ import annotations

import logging
import secrets
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone

from certificates.eligibility import is_eligible_for_certificate, overall_score_for
from certificates.models import CertificateTemplate, IssuedCertificate
from certificates.services.generator import generate_certificate_pdf
from certificates.services.qr import build_verification_url

logger = logging.getLogger(__name__)


class CertificateIssuanceError(Exception):
    """User-facing issuance failure."""


def get_user_certificate(user) -> IssuedCertificate | None:
    return (
        IssuedCertificate.objects.filter(user=user)
        .select_related("template", "user")
        .first()
    )


def get_ready_certificate(user) -> IssuedCertificate | None:
    """Only certificates that already have a stored PDF."""
    cert = get_user_certificate(user)
    if cert and cert.pdf_file:
        return cert
    return None


def _is_staff(user) -> bool:
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def certificate_needs_template_refresh(user) -> bool:
    """True when staff has an issued PDF that does not match the active admin template."""
    if not _is_staff(user):
        return False
    cert = get_ready_certificate(user)
    active = CertificateTemplate.get_active()
    if not cert or not active:
        return False
    return cert.template_id != active.pk


def _make_certificate_id() -> str:
    year = timezone.now().year
    return f"CQ-{year}-{secrets.token_hex(4).upper()}"


def _make_verification_token() -> str:
    return secrets.token_urlsafe(32)


def _unique_certificate_id() -> str:
    for _ in range(12):
        candidate = _make_certificate_id()
        if not IssuedCertificate.objects.filter(certificate_id=candidate).exists():
            return candidate
    raise CertificateIssuanceError("Could not allocate a unique certificate ID.")


def _recipient_name(user) -> str:
    name = (getattr(user, "full_name", None) or "").strip()
    if name:
        return name
    display = user.display_name() if hasattr(user, "display_name") else ""
    display = (display or "").strip()
    if display:
        return display
    return (user.email or "CyberQuest Learner").split("@")[0]


def _format_issue_date(dt) -> str:
    local = timezone.localtime(dt)
    return local.strftime("%d %B %Y")


def _resolve_score(user, existing: IssuedCertificate | None, *, regenerating: bool) -> int:
    live_score = overall_score_for(user)
    if live_score == 0 and _is_staff(user):
        live_score = 100
    if existing is None or regenerating:
        return live_score
    if int(existing.score or 0) == 0:
        return live_score
    return int(existing.score)


@transaction.atomic
def issue_certificate_for_user(user, request=None, *, force: bool = False) -> IssuedCertificate:
    """
    Generate and persist a certificate for an eligible user.

    Normal users: if a PDF already exists, return it (no regenerate).
    Staff: pass force=True to rebuild using the current active admin template.
    """
    existing = (
        IssuedCertificate.objects.select_for_update()
        .filter(user=user)
        .first()
    )

    regenerating = False
    if existing and existing.pdf_file:
        if force:
            if not _is_staff(user):
                raise CertificateIssuanceError("Only staff can regenerate a certificate.")
            regenerating = True
        else:
            return existing

    if not is_eligible_for_certificate(user):
        raise CertificateIssuanceError(
            "You are not eligible for a certificate yet."
        )

    # Always prefer the current active template for new issues / staff regenerations.
    active_template = CertificateTemplate.get_active()
    live_name = _recipient_name(user)
    score = _resolve_score(user, existing, regenerating=regenerating)

    if existing is None:
        recipient = live_name
        template = active_template
        issued_at = timezone.now()
        certificate_id = _unique_certificate_id()
        verification_token = _make_verification_token()
    else:
        recipient = live_name if regenerating or not (existing.recipient_name or "").strip() else existing.recipient_name
        template = active_template if regenerating else (existing.template or active_template)
        issued_at = existing.issued_at or timezone.now()
        certificate_id = existing.certificate_id
        verification_token = existing.verification_token or _make_verification_token()

    if template is None:
        logger.warning(
            "No active CertificateTemplate; generating default design for user %s",
            user.pk,
        )

    verify_url = build_verification_url(certificate_id, request=request)

    try:
        pdf_bytes = generate_certificate_pdf(
            recipient_name=recipient,
            score=score,
            certificate_id=certificate_id,
            issued_date_display=_format_issue_date(issued_at),
            verify_url=verify_url,
            template=template,
            require_template=bool(template),
        )
    except Exception as exc:
        logger.exception("PDF generation failed for user %s", user.pk)
        raise CertificateIssuanceError(
            f"Certificate generation failed: {exc}"
        ) from None

    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        raise CertificateIssuanceError("Generated certificate was invalid.")

    filename = f"{certificate_id}.pdf"
    try:
        if existing:
            existing.score = score
            existing.recipient_name = recipient
            existing.verification_token = verification_token
            existing.template = template
            if not existing.issued_at:
                existing.issued_at = issued_at
            # Replace stored PDF (important for staff regenerate with new template).
            if existing.pdf_file:
                existing.pdf_file.delete(save=False)
            existing.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
            existing.save()
            return existing

        cert = IssuedCertificate(
            user=user,
            template=template,
            certificate_id=certificate_id,
            verification_token=verification_token,
            recipient_name=recipient,
            score=score,
            issued_at=issued_at,
        )
        cert.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
        cert.save()
    except IntegrityError:
        raced = IssuedCertificate.objects.filter(user=user).first()
        if raced:
            return raced
        raise CertificateIssuanceError("Could not save certificate. Please retry.")
    except Exception:
        logger.exception("Storage failure saving certificate for user %s", user.pk)
        raise CertificateIssuanceError(
            "Could not store the certificate file. Please try again."
        ) from None

    return cert
