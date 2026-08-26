from django.contrib import admin
from .models import Badge, UserBadge


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("icon_emoji", "name", "code", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name", "code")


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    """Read-only view of who earned what, and when."""
    list_display = ("user", "badge", "earned_at")
    list_filter = ("badge",)
    search_fields = ("user__email", "user__username")
    ordering = ("-earned_at",)
