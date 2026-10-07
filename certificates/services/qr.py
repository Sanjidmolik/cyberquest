"""Server-side QR code generation for certificate verification URLs."""

from __future__ import annotations

import io

import qrcode
from django.conf import settings
from django.urls import reverse


def build_verification_url(certificate_id: str, request=None) -> str:
    """
    Prefer PUBLIC_BASE_URL (Render/production), then the current request host,
    and finally a safe localhost fallback for tests.
    """
    # Canonical public path used in QR codes: /verify/<certificate_id>/
    path = reverse("certificate_verify", kwargs={"certificate_id": certificate_id})
    base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
    if base:
        return f"{base}{path}"
    if request is not None:
        return request.build_absolute_uri(path)
    return f"http://127.0.0.1:8000{path}"


def make_qr_png_bytes(payload: str, box_size: int = 8, border: int = 2) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
