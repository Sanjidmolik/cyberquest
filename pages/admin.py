from django.contrib import admin
from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "submitted_at", "is_resolved")
    list_editable = ("is_resolved",)
    list_filter = ("is_resolved",)
    search_fields = ("name", "email", "message")
