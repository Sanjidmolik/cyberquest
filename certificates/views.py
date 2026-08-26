"""
certificates/views.py
--------------------------
Generates a downloadable PDF certificate for users who have completed
the full CyberQuest course curriculum (see eligibility.py for the exact
rule). The PDF is built entirely in memory -- nothing is saved to disk,
it's streamed straight to the browser as a download.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import HttpResponse
from io import BytesIO

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

from .eligibility import is_eligible_for_certificate

GREEN = HexColor("#1F9C53")
DARK = HexColor("#0D1117")


@login_required(login_url="/accounts/login/")
def certificate_page(request):
    """Shows either the 'here's your certificate' page or what's still needed."""
    eligible = is_eligible_for_certificate(request.user)
    return render(request, "certificates/certificate_page.html", {"eligible": eligible})


@login_required(login_url="/accounts/login/")
def certificate_download(request):
    """Generates and streams the actual PDF -- only if the user has earned it."""
    if not is_eligible_for_certificate(request.user):
        return HttpResponse("You have not yet completed the requirements for a certificate.", status=403)

    buffer = BytesIO()
    page_size = landscape(letter)
    c = canvas.Canvas(buffer, pagesize=page_size)
    width, height = page_size

    # Border
    c.setStrokeColor(GREEN)
    c.setLineWidth(4)
    c.rect(0.4 * inch, 0.4 * inch, width - 0.8 * inch, height - 0.8 * inch)

    # Title
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(width / 2, height - 1.6 * inch, "CyberQuest")

    c.setFillColor(DARK)
    c.setFont("Helvetica", 16)
    c.drawCentredString(width / 2, height - 2.1 * inch, "Certificate of Completion")

    c.setFont("Helvetica", 13)
    c.drawCentredString(width / 2, height - 2.9 * inch, "This certifies that")

    display_name = request.user.display_name()
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(width / 2, height - 3.6 * inch, display_name)

    c.setFont("Helvetica", 13)
    c.drawCentredString(
        width / 2, height - 4.2 * inch,
        "has successfully completed the CyberQuest cybersecurity training curriculum"
    )

    c.setFont("Helvetica", 10)
    from django.utils import timezone
    c.drawCentredString(width / 2, height - 5.0 * inch, f"Issued on {timezone.now():%B %d, %Y}")

    c.showPage()
    c.save()
    buffer.seek(0)

    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="CyberQuest_Certificate_{request.user.username or request.user.pk}.pdf"'
    return response
