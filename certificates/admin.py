from django.contrib import admin
from django.contrib.admin.widgets import AdminFileWidget
from django.urls import reverse
from django.utils.html import format_html

from .models import CertificateTemplate, IssuedCertificate, Signatory


class ProtectedFileWidget(AdminFileWidget):
    """Point the current-file link at an authenticated route instead of /media/."""

    template_name = "certificates/protected_file_input.html"

    def __init__(self, url_name, attrs=None):
        self.url_name = url_name
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        instance = getattr(value, "instance", None)
        download_url = ""
        if instance is not None and getattr(instance, "pk", None):
            download_url = reverse(self.url_name, args=[instance.pk])
        context["widget"]["download_url"] = download_url
        return context


@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at", "updated_at", "pdf_link")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-is_active", "-updated_at")
    fieldsets = (
        (None, {
            "fields": ("name", "pdf_file", "is_active"),
            "description": (
                "Template may be PDF, JPG, or PNG. Users always receive a generated PDF."
            ),
        }),
        ("Field coordinates (optional)", {
            "classes": ("collapse",),
            "description": (
                "For JPG/PNG (and PDFs without {{NAME}} / {{SCORE}} / {{DATE}} / "
                "{{CERTIFICATE_ID}} / {{QR}} placeholders). Use page/image coordinates."
            ),
            "fields": ("field_config",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "pdf_file":
            kwargs["widget"] = ProtectedFileWidget("certificates:template_file")
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="Template")
    def pdf_link(self, obj):
        if obj.pdf_file:
            return format_html(
                '<a href="{}" target="_blank">Open</a>',
                reverse("certificates:template_file", args=[obj.pk]),
            )
        return "—"


@admin.register(IssuedCertificate)
class IssuedCertificateAdmin(admin.ModelAdmin):
    list_display = (
        "certificate_id",
        "user",
        "recipient_name",
        "score",
        "issued_at",
        "template",
        "has_pdf",
    )
    list_filter = ("issued_at", "template")
    search_fields = (
        "certificate_id",
        "recipient_name",
        "user__email",
        "user__username",
        "user__full_name",
        "verification_token",
    )
    ordering = ("-issued_at",)
    exclude = ("pdf_file",)
    readonly_fields = (
        "certificate_id",
        "verification_token",
        "user",
        "template",
        "recipient_name",
        "score",
        "issued_at",
        "pdf_link",
        "created_at",
    )
    autocomplete_fields = ()

    @admin.display(boolean=True, description="PDF")
    def has_pdf(self, obj):
        return bool(obj.pdf_file)

    @admin.display(description="PDF file")
    def pdf_link(self, obj):
        if not obj.pdf_file:
            return "—"
        return format_html(
            '<a href="{}">{}</a>',
            reverse("certificates:issued_file", args=[obj.pk]),
            obj.pdf_file.name,
        )

    def has_add_permission(self, request):
        return False


@admin.register(Signatory)
class SignatoryAdmin(admin.ModelAdmin):
    list_display = ("name", "title", "order", "is_active", "signature_link")

    @admin.display(description="Signature")
    def signature_link(self, obj):
        if obj.signature_image:
            return format_html(
                '<a href="{}" target="_blank">Open</a>',
                reverse("certificates:signature_file", args=[obj.pk]),
            )
        return "—"
    list_editable = ("order", "is_active")
    ordering = ("order",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "signature_image":
            kwargs["widget"] = ProtectedFileWidget("certificates:signature_file")
        return super().formfield_for_dbfield(db_field, request, **kwargs)
