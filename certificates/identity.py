"""
certificates/identity.py
----------------------------
ONE JOB: get-or-create a stable certificate_id for a user. Called every
time someone views/downloads their certificate -- returns the SAME id
on every call after the first, so the QR code always points to a
verification link that keeps working.
"""

import secrets
from django.utils import timezone
from .models import IssuedCertificate


def get_or_create_certificate(user) -> IssuedCertificate:
    existing = IssuedCertificate.objects.filter(user=user).first()
    if existing:
        return existing

    year = timezone.now().year
    random_part = secrets.token_hex(4).upper()
    certificate_id = f"CQ-{year}-{random_part}"

    while IssuedCertificate.objects.filter(certificate_id=certificate_id).exists():
        random_part = secrets.token_hex(4).upper()
        certificate_id = f"CQ-{year}-{random_part}"

    return IssuedCertificate.objects.create(user=user, certificate_id=certificate_id)