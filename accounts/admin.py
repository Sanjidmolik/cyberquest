"""
accounts/admin.py
--------------------
Registers CustomUser with Django's built-in admin panel, so you can view
and manage users at http://127.0.0.1:8000/admin/
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


class CustomUserAdmin(UserAdmin):
    """Tells the admin site how to display/edit our email-based user."""
    model = CustomUser

    # Columns shown in the main "Custom users" list page
    list_display = (
        "email", "username", "cyber_class", "skill_level",
        "level", "xp", "is_staff", "is_active", "date_joined",
    )
    list_filter = ("cyber_class", "skill_level", "is_active", "is_staff")
    ordering = ("-date_joined",)

    # Since we removed the default "username" behavior, redefine these fieldsets
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": (
            "username", "full_name", "date_of_birth",
            "cyber_class", "skill_level", "ethical_agreement",
        )}),
        ("Gamification", {"fields": ("xp", "level")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "username", "password1", "password2"),
        }),
    )
    search_fields = ("email", "username")

    # ---- Bulk actions: select one or more users in the list, then choose
    # one of these from the "Action" dropdown, to promote/demote them ----
    actions = ["make_admin", "remove_admin"]

    @admin.action(description="Make selected users ADMIN (staff access)")
    def make_admin(self, request, queryset):
        updated_count = queryset.update(is_staff=True)
        self.message_user(request, f"{updated_count} user(s) granted admin/staff access.")

    @admin.action(description="Remove ADMIN access from selected users")
    def remove_admin(self, request, queryset):
        # Safety: never let someone accidentally strip their OWN admin
        # access via a bulk action while logged in as themselves.
        queryset = queryset.exclude(pk=request.user.pk)
        updated_count = queryset.update(is_staff=False)
        self.message_user(request, f"Admin access removed from {updated_count} user(s).")


admin.site.register(CustomUser, CustomUserAdmin)
