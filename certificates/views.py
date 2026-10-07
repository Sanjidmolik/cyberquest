"""
Certificate dashboard, generation, download, and public verification.
"""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .eligibility import get_eligibility_status
from .services.issuance import (
    CertificateIssuanceError,
    certificate_needs_template_refresh,
    get_ready_certificate,
    get_user_certificate,
    issue_certificate_for_user,
)
from .models import CertificateTemplate, IssuedCertificate
from .services.qr import build_verification_url

logger = logging.getLogger(__name__)


def _page_context(request):
    user = request.user
    status = get_eligibility_status(user)
    # Only show as "issued" when a real PDF exists (legacy ID-only rows are incomplete).
    certificate = get_ready_certificate(user)
    pending = None
    if certificate is None:
        raw = get_user_certificate(user)
        if raw and not raw.pdf_file:
            pending = raw

    verify_url = None
    if certificate:
        verify_url = build_verification_url(certificate.certificate_id, request=request)

    active_template = CertificateTemplate.get_active()
    return {
        "status": status,
        "eligible": status["eligible"],
        "certificate": certificate,
        "pending_certificate": pending,
        "verify_url": verify_url,
        "display_name": user.display_name(),
        "active_template": active_template,
        "needs_template_refresh": certificate_needs_template_refresh(user),
        "is_staff_user": bool(user.is_staff or user.is_superuser),
    }


def _serve_pdf(cert, *, as_attachment: bool):
    try:
        return FileResponse(
            cert.pdf_file.open("rb"),
            as_attachment=as_attachment,
            filename=f"CyberQuest_{cert.certificate_id}.pdf",
            content_type="application/pdf",
        )
    except Exception:
        logger.exception("Certificate file serve failed for %s", cert.certificate_id)
        return HttpResponse("Could not open certificate.", status=500)


def _ensure_ready_certificate(request):
    """
    Return a certificate with a PDF for the current user.
    Backfills legacy ID-only rows when the user is eligible.
    """
    ready = get_ready_certificate(request.user)
    if ready:
        return ready
    return issue_certificate_for_user(request.user, request=request)


@login_required(login_url="/accounts/login/")
def certificate_page(request):
    return render(request, "certificates/certificate_page.html", _page_context(request))


@login_required(login_url="/accounts/login/")
@require_POST
def certificate_generate(request):
    force = request.POST.get("force") == "1" and (
        request.user.is_staff or request.user.is_superuser
    )
    try:
        cert = issue_certificate_for_user(request.user, request=request, force=force)
        if force:
            messages.success(
                request,
                f"Certificate {cert.certificate_id} regenerated with the active template.",
            )
        else:
            messages.success(request, f"Certificate {cert.certificate_id} is ready.")
    except CertificateIssuanceError as exc:
        messages.error(request, str(exc))
    except Exception:
        logger.exception("Unexpected certificate generation error")
        messages.error(request, "Something went wrong generating your certificate.")
    return redirect("certificates:page")


@login_required(login_url="/accounts/login/")
def certificate_download(request):
    try:
        cert = _ensure_ready_certificate(request)
    except CertificateIssuanceError as exc:
        messages.error(request, str(exc))
        return redirect("certificates:page")
    except Exception:
        logger.exception("Certificate download ensure failed")
        messages.error(request, "Could not prepare your certificate PDF.")
        return redirect("certificates:page")
    return _serve_pdf(cert, as_attachment=True)


@login_required(login_url="/accounts/login/")
def certificate_view_pdf(request):
    """Inline PDF view for the owner."""
    try:
        cert = _ensure_ready_certificate(request)
    except CertificateIssuanceError as exc:
        messages.error(request, str(exc))
        return redirect("certificates:page")
    except Exception:
        logger.exception("Certificate view ensure failed")
        messages.error(request, "Could not prepare your certificate PDF.")
        return redirect("certificates:page")
    return _serve_pdf(cert, as_attachment=False)


def verify_certificate(request, certificate_id):
    certificate = (
        IssuedCertificate.objects.filter(certificate_id=certificate_id)
        .select_related("user")
        .first()
    )
    # Treat ID-only legacy rows without a PDF as not yet issued/valid.
    found = certificate is not None and bool(certificate.pdf_file)
    context = {
        "found": found,
        "valid": found,
        "certificate": certificate if found else None,
        "certificate_id": certificate_id,
    }
    return render(request, "certificates/verify.html", context)
