import secrets

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def fill_existing_certificates(apps, schema_editor):
    IssuedCertificate = apps.get_model("certificates", "IssuedCertificate")
    for cert in IssuedCertificate.objects.all():
        user = cert.user
        if not cert.recipient_name:
            name = (getattr(user, "full_name", None) or "").strip()
            if not name:
                name = (getattr(user, "username", None) or "") or user.email.split("@")[0]
            cert.recipient_name = name[:200]
        if cert.score is None:
            cert.score = 0
        if not cert.verification_token:
            cert.verification_token = secrets.token_urlsafe(32)
        if cert.created_at is None:
            cert.created_at = cert.issued_at
        cert.save()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("certificates", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CertificateTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150)),
                (
                    "pdf_file",
                    models.FileField(
                        help_text="Upload a PDF certificate design. Prefer placeholders {{NAME}}, {{SCORE}}, {{DATE}}, {{CERTIFICATE_ID}}, {{QR}} or configure field coordinates below.",
                        upload_to="certificate_templates/",
                        validators=[
                            django.core.validators.FileExtensionValidator(["pdf"]),
                        ],
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=False,
                        help_text="When activated, this becomes the template used for newly issued certificates.",
                    ),
                ),
                (
                    "field_config",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Optional overlay coordinates when the PDF has no {{PLACEHOLDER}} markers.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-is_active", "-updated_at"],
            },
        ),
        migrations.AlterField(
            model_name="signatory",
            name="signature_image",
            field=models.ImageField(
                blank=True,
                help_text="Optional scanned signature image.",
                null=True,
                upload_to="signatures/",
            ),
        ),
        migrations.AddField(
            model_name="issuedcertificate",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name="issuedcertificate",
            name="pdf_file",
            field=models.FileField(blank=True, upload_to="issued_certificates/"),
        ),
        migrations.AddField(
            model_name="issuedcertificate",
            name="recipient_name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="issuedcertificate",
            name="score",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Overall competency score (%) frozen at issue time.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="issuedcertificate",
            name="verification_token",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="issuedcertificate",
            name="template",
            field=models.ForeignKey(
                blank=True,
                help_text="Template used at issue time (null = built-in default design).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="issued_certificates",
                to="certificates.certificatetemplate",
            ),
        ),
        migrations.RunPython(fill_existing_certificates, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="issuedcertificate",
            name="recipient_name",
            field=models.CharField(max_length=200),
        ),
        migrations.AlterField(
            model_name="issuedcertificate",
            name="score",
            field=models.PositiveSmallIntegerField(
                help_text="Overall competency score (%) frozen at issue time.",
            ),
        ),
        migrations.AlterField(
            model_name="issuedcertificate",
            name="verification_token",
            field=models.CharField(db_index=True, max_length=64, unique=True),
        ),
        migrations.AlterField(
            model_name="issuedcertificate",
            name="certificate_id",
            field=models.CharField(db_index=True, max_length=40, unique=True),
        ),
        migrations.AlterField(
            model_name="issuedcertificate",
            name="issued_at",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="issuedcertificate",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterModelOptions(
            name="issuedcertificate",
            options={"ordering": ["-issued_at"]},
        ),
    ]
