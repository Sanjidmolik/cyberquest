"""
certificates/models.py
----------------------
CertificateTemplate  -- admin-uploaded designs (PDF / JPG / PNG)
IssuedCertificate    -- frozen, once-generated certificate PDF for a user
Signatory            -- optional signature lines for the default PDF design
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models, transaction

TEMPLATE_EXTENSIONS = ("pdf", "jpg", "jpeg", "png")
TEMPLATE_MAX_BYTES = 10 * 1024 * 1024


def validate_template_file(value):
    name = (getattr(value, "name", "") or "").lower()
    if not name.endswith(tuple(f".{ext}" for ext in TEMPLATE_EXTENSIONS)):
        raise ValidationError("Only PDF, JPG, or PNG files are allowed.")
    size = getattr(value, "size", None)
    if size is not None and size > TEMPLATE_MAX_BYTES:
        raise ValidationError("Template file must be 10 MB or smaller.")


class CertificateTemplate(models.Model):
    """Admin-managed certificate design used as the foundation for new issues."""

    name = models.CharField(max_length=150)
    # Kept as pdf_file in DB for compatibility; accepts PDF/JPG/PNG templates.
    pdf_file = models.FileField(
        upload_to="certificate_templates/",
        validators=[FileExtensionValidator(list(TEMPLATE_EXTENSIONS)), validate_template_file],
        help_text=(
            "Upload a certificate design: PDF, JPG, or PNG. "
            "For PDFs, prefer placeholders {{NAME}}, {{SCORE}}, {{DATE}}, "
            "{{CERTIFICATE_ID}}, {{QR}}. For images (and PDFs without placeholders), "
            "set field coordinates below. Issued certificates are always saved as PDF."
        ),
        verbose_name="Template file",
    )
    is_active = models.BooleanField(
        default=False,
        help_text="When activated, this becomes the template used for newly issued certificates.",
    )
    # Absolute page coordinates (points) when placeholders are absent / image templates.
    # Example keys: name, score, date, certificate_id, qr
    # Each value: {"x": 0, "y": 0, "w": 400, "h": 40, "fontsize": 28}  (qr uses "size")
    field_config = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Overlay coordinates (PDF points). Required for JPG/PNG templates; "
            "optional for PDFs that already contain {{PLACEHOLDER}} text."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "-updated_at"]

    def __str__(self):
        status = "active" if self.is_active else "inactive"
        return f"{self.name} ({status})"

    def delete(self, using=None, keep_parents=False):
        permanent = (self.pdf_file.name or "").replace("\\", "/").endswith(
            "CyberQuest_Certificate_of_Achievement.pdf"
        )
        if permanent:
            # The built-in design file also backs certificates issued with no upload.
            self.pdf_file.delete = lambda save=True: None
        super().delete(using=using, keep_parents=keep_parents)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
            if self.is_active:
                (
                    type(self).objects.select_for_update()
                    .exclude(pk=self.pk)
                    .filter(is_active=True)
                    .update(is_active=False)
                )

    @classmethod
    def get_active(cls):
        return cls.objects.filter(is_active=True).order_by("-updated_at").first()

    @property
    def template_kind(self) -> str:
        name = (self.pdf_file.name or "").lower()
        if name.endswith(".pdf"):
            return "pdf"
        if name.endswith((".jpg", ".jpeg", ".png")):
            return "image"
        return "unknown"


class IssuedCertificate(models.Model):
    """
    A permanently stored certificate PDF for one user.
    Score / name / issue time are frozen at generation and never recalculated.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="certificate",
    )
    template = models.ForeignKey(
        CertificateTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issued_certificates",
        help_text="Template used at issue time (null = built-in default design).",
    )
    certificate_id = models.CharField(max_length=40, unique=True, db_index=True)
    verification_token = models.CharField(max_length=64, unique=True, db_index=True)
    recipient_name = models.CharField(max_length=200)
    score = models.PositiveSmallIntegerField(
        help_text="Overall competency score (%) frozen at issue time.",
    )
    issued_at = models.DateTimeField()
    pdf_file = models.FileField(upload_to="issued_certificates/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return f"{self.certificate_id} — {self.user.email}"


class Signatory(models.Model):
    """Optional admin-managed signature lines for the default certificate design."""

    name = models.CharField(max_length=150)
    title = models.CharField(
        max_length=150,
        help_text="e.g. 'Head of CyberQuest' or 'Course Director'",
    )
    signature_image = models.ImageField(
        upload_to="signatures/",
        blank=True,
        null=True,
        help_text="Optional scanned signature image.",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Left-to-right display order on the default certificate.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive signatories are omitted from newly generated default certificates.",
    )

    class Meta:
        ordering = ["order"]
        verbose_name_plural = "Signatories"

    def __str__(self):
        return f"{self.name} ({self.title})"
