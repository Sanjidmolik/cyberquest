from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, VerificationCode


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ("email", "username", "google_linked", "email_verified", "is_staff", "is_active", "date_joined")
    list_filter = ("google_linked", "email_verified", "is_active", "is_staff")
    ordering = ("-date_joined",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("username", "full_name", "date_of_birth", "cyber_class", "skill_level",
                                 "ethical_agreement", "google_linked", "profile_picture",
                                 "email_2fa_enabled", "totp_enabled", "email_verified")}),
        ("Gamification", {"fields": ("xp", "level")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "username", "password1", "password2")}),)
    search_fields = ("email", "username")

    actions = ["make_admin", "remove_admin", "suspend_accounts", "reactivate_accounts"]

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # Phase 1 — Step 5: link the photo through the protected view, never a bucket URL.
        if db_field.name == "profile_picture":
            from certificates.admin import ProtectedFileWidget

            kwargs["widget"] = ProtectedFileWidget("accounts:profile_photo")
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.action(description="Make selected users ADMIN (staff access)")
    def make_admin(self, request, queryset):
        queryset.update(is_staff=True)

    @admin.action(description="Remove ADMIN access from selected users")
    def remove_admin(self, request, queryset):
        queryset.exclude(pk=request.user.pk).update(is_staff=False)

    @admin.action(description="Suspend selected accounts (block login)")
    def suspend_accounts(self, request, queryset):
        queryset.exclude(pk=request.user.pk).update(is_active=False)

    @admin.action(description="Reactivate selected accounts")
    def reactivate_accounts(self, request, queryset):
        queryset.update(is_active=True)


admin.site.register(CustomUser, CustomUserAdmin)


@admin.register(VerificationCode)
class VerificationCodeAdmin(admin.ModelAdmin):
    """Audit view only. The code itself is never stored, so there is nothing to reveal."""

    list_display = ("user", "purpose", "created_at", "expires_at", "is_used")
    list_filter = ("purpose", "is_used")
    search_fields = ("user__email",)
    exclude = ("code_hash",)
    readonly_fields = ("user", "purpose", "created_at", "expires_at", "is_used")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
