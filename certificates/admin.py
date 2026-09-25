from django.contrib import admin
from .models import Signatory, IssuedCertificate


@admin.register(Signatory)
class SignatoryAdmin(admin.ModelAdmin):
    list_display = ("name", "title", "order", "is_active")
    list_editable = ("order", "is_active")
    ordering = ("order",)


@admin.register(IssuedCertificate)
class IssuedCertificateAdmin(admin.ModelAdmin):
    list_display = ("certificate_id", "user", "issued_at")
    search_fields = ("certificate_id", "user__email", "user__username")
    ordering = ("-issued_at",)
    readonly_fields = ("certificate_id", "user", "issued_at")

    def has_add_permission(self, request):
        return False