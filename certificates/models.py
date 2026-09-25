"""
certificates/models.py
--------------------------
Signatory     -- admin-managed: name, title, and an uploaded signature
                 image, shown at the bottom of every generated certificate.
IssuedCertificate -- records a stable certificate_id the first time a
                 user downloads their certificate, so re-downloading
                 doesn't generate a new ID each time, and so the QR
                 code's verification link always resolves to something.
"""

from django.conf import settings
from django.db import models


class Signatory(models.Model):
    """A person whose signature appears on the certificate (admin-managed)."""

    name = models.CharField(max_length=150)
    title = models.CharField(max_length=150, help_text="e.g. 'Head of CyberQuest' or 'Founder & Director'")
    signature_image = models.ImageField(
        upload_to="signatures/",
        help_text="A scanned/photographed signature, ideally on a transparent or white background.",
    )
    order = models.PositiveIntegerField(default=0, help_text="Left-to-right display order on the certificate.")
    is_active = models.BooleanField(default=True, help_text="Inactive signatories are omitted from new certificates.")

    class Meta:
        ordering = ["order"]
        verbose_name_plural = "Signatories"

    def __str__(self):
        return f"{self.name} ({self.title})"


class IssuedCertificate(models.Model):
    """One stable record per user, created the first time they download their certificate."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="certificate")
    certificate_id = models.CharField(max_length=30, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.certificate_id} — {self.user.email}"