from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpResponse
import io
import base64
import qrcode

from .eligibility import is_eligible_for_certificate
from .identity import get_or_create_certificate
from .competency import get_competency_profile, competency_band
from .models import Signatory


def _build_context(request):
    user = request.user
    certificate = get_or_create_certificate(user)
    profile = get_competency_profile(user)
    scores = {c["game_key"]: c["percent"] for c in profile["categories"]}
    overall = profile["overall_score"]
    level = competency_band(overall)

    # Real QR code pointing to this certificate's public verification page,
    # embedded as a data URI so it renders inline in BOTH the on-screen
    # HTML page and the WeasyPrint-generated PDF, with no separate file.
    verify_url = request.build_absolute_uri(f"/certificate/verify/{certificate.certificate_id}/")
    qr_img = qrcode.make(verify_url)
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_base64 = base64.b64encode(qr_buffer.getvalue()).decode("utf-8")
    qr_data_uri = f"data:image/png;base64,{qr_base64}"

    return {
        "eligible": is_eligible_for_certificate(user),
        "display_name": user.display_name(),
        "certificate_id": certificate.certificate_id,
        "issued_date": certificate.issued_at,
        "phishing_score": scores.get("phishing_simulator", 0),
        "password_score": scores.get("password_cracker", 0),
        "network_score": scores.get("network_defense", 0),
        "cryptography_score": scores.get("cryptography", 0),
        "osint_score": scores.get("osint", 0),
        "overall_score": overall,
        "competency_level": level,
        "signatories": Signatory.objects.filter(is_active=True).order_by("order"),
        "qr_code": qr_data_uri,
    }


@login_required(login_url="/accounts/login/")
def certificate_page(request):
    return render(request, "certificates/certificate_page.html", _build_context(request))


@login_required(login_url="/accounts/login/")
def certificate_download(request):
    """
    Renders the SAME template as the on-screen page, then converts that
    exact HTML/CSS to a PDF via WeasyPrint -- guaranteeing the download
    always matches what you see on screen, since it's the same source.
    """
    if not is_eligible_for_certificate(request.user):
        return HttpResponse("Complete all courses and games to unlock your certificate.", status=403)

    from django.template.loader import render_to_string
    from weasyprint import HTML

    html_string = render_to_string(
        "certificates/certificate_page.html", _build_context(request), request=request
    )
    pdf_bytes = HTML(string=html_string, base_url=request.build_absolute_uri("/")).write_pdf()

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="CyberQuest_Certificate_{request.user.username}.pdf"'
    return response


def verify_certificate(request, certificate_id):
    from .models import IssuedCertificate
    certificate = IssuedCertificate.objects.filter(certificate_id=certificate_id).select_related("user").first()
    return render(request, "certificates/verify.html", {
        "certificate": certificate, "found": certificate is not None,
    })