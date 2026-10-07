import django.core.validators
from django.db import migrations, models

import certificates.models


class Migration(migrations.Migration):

    dependencies = [
        ("certificates", "0002_certificate_system_redesign"),
    ]

    operations = [
        migrations.AlterField(
            model_name="certificatetemplate",
            name="pdf_file",
            field=models.FileField(
                help_text=(
                    "Upload a certificate design: PDF, JPG, or PNG. "
                    "For PDFs, prefer placeholders {{NAME}}, {{SCORE}}, {{DATE}}, "
                    "{{CERTIFICATE_ID}}, {{QR}}. For images (and PDFs without placeholders), "
                    "set field coordinates below. Issued certificates are always saved as PDF."
                ),
                upload_to="certificate_templates/",
                validators=[
                    django.core.validators.FileExtensionValidator(["pdf", "jpg", "jpeg", "png"]),
                    certificates.models.validate_template_file,
                ],
                verbose_name="Template file",
            ),
        ),
        migrations.AlterField(
            model_name="certificatetemplate",
            name="field_config",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "Overlay coordinates (PDF points). Required for JPG/PNG templates; "
                    "optional for PDFs that already contain {{PLACEHOLDER}} text."
                ),
            ),
        ),
    ]
