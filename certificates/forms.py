"""Admin form for certificate templates. Uses the existing CertificateTemplate model."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse

from certificates.layout import activation_errors, normalize_field_config, placeholder_report
from certificates.models import TEMPLATE_EXTENSIONS, CertificateTemplate
from certificates.services.generator import editor_field_config


class TemplateFileInput(forms.ClearableFileInput):
    template_name = "dashboard/ops/template_file_input.html"

    def __init__(self, download_url="", attrs=None):
        self.download_url = download_url
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["download_url"] = self.download_url
        return context


class CertificateTemplateForm(forms.ModelForm):
    class Meta:
        model = CertificateTemplate
        fields = ["name", "pdf_file", "is_active", "field_config"]
        labels = {
            "name": "Template name",
            "pdf_file": "Template file",
            "is_active": "Active template",
            "field_config": "Field coordinates",
        }
        help_texts = {
            "pdf_file": "PDF, JPG, or PNG. Issued certificates are always saved as PDF.",
            "is_active": "New certificates use the active template. Previously issued PDFs stay as they were.",
            "field_config": "Stored automatically from the visual builder.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "off"}),
            "pdf_file": forms.ClearableFileInput(attrs={"accept": ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"}),
            "field_config": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.layout_warnings: list[str] = []
        self.fields["pdf_file"].required = not bool(getattr(self.instance, "pk", None))
        if getattr(self.instance, "pk", None):
            self.fields["pdf_file"].widget = TemplateFileInput(
                download_url=reverse("certificates:template_file", args=[self.instance.pk]),
            )

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise ValidationError("Enter a template name.")
        return name

    def clean_field_config(self):
        raw = self.cleaned_data.get("field_config")
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return {}
            try:
                raw = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"Field coordinates are not valid JSON ({exc.msg}).") from exc
        try:
            return normalize_field_config(raw)
        except ValidationError:
            raise

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        upload = cleaned.get("pdf_file")
        path, kind, temporary = _template_path(upload, self.instance)
        if path is None:
            return cleaned
        try:
            try:
                report = placeholder_report(path, kind)
            except Exception as exc:
                raise ValidationError(f"Could not read the template file ({exc}).") from exc
            self.layout_warnings = [f"Unsupported placeholder {token}." for token in report["unknown"]]
            config = cleaned.get("field_config") or {}
            if cleaned.get("is_active"):
                effective = editor_field_config(path, kind, config)
                problems = activation_errors(path, kind, effective)
                if problems:
                    raise ValidationError(problems)
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)
        return cleaned


def _template_path(upload, instance):
    name = ""
    if upload is not None and getattr(upload, "name", None):
        name = upload.name
        suffix = Path(name).suffix.lower().lstrip(".")
        if suffix == "jpeg":
            suffix = "jpg"
        if suffix not in TEMPLATE_EXTENSIONS and suffix != "jpeg":
            return None, "unknown", None
        if hasattr(upload, "temporary_file_path"):
            try:
                return upload.temporary_file_path(), "pdf" if name.lower().endswith(".pdf") else "image", None
            except Exception:
                pass
        if hasattr(upload, "read"):
            payload = upload.read()
            if hasattr(upload, "seek"):
                upload.seek(0)
            handle = tempfile.NamedTemporaryFile(delete=False, suffix=Path(name).suffix)
            handle.write(payload)
            handle.close()
            kind = "pdf" if name.lower().endswith(".pdf") else "image"
            return handle.name, kind, handle.name
    stored = getattr(instance, "pdf_file", None)
    if stored and getattr(stored, "name", None):
        try:
            return stored.path, instance.template_kind, None
        except Exception:
            return None, instance.template_kind, None
    return None, "unknown", None
