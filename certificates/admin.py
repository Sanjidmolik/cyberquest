from django.contrib import admin
from django.utils.html import format_html

from .models import CertificateTemplate, IssuedCertificate, Signatory


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

    @admin.display(description="Template")
    def pdf_link(self, obj):
        if obj.pdf_file:
            return format_html('<a href="{}" target="_blank">Open</a>', obj.pdf_file.url)
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
    readonly_fields = (
        "certificate_id",
        "verification_token",
        "user",
        "template",
        "recipient_name",
        "score",
        "issued_at",
        "pdf_file",
        "created_at",
    )
    autocomplete_fields = ()

    @admin.display(boolean=True, description="PDF")
    def has_pdf(self, obj):
        return bool(obj.pdf_file)

    def has_add_permission(self, request):
        return False


@admin.register(Signatory)
class SignatoryAdmin(admin.ModelAdmin):
    list_display = ("name", "title", "order", "is_active")
    list_editable = ("order", "is_active")
    ordering = ("order",)
