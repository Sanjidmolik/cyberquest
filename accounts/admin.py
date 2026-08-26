from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, VerificationCode


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ("email", "username", "google_linked", "is_staff", "is_active", "date_joined")
    list_filter = ("google_linked", "is_active", "is_staff")
    ordering = ("-date_joined",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("username", "full_name", "date_of_birth", "cyber_class", "skill_level",
                                 "ethical_agreement", "google_linked", "profile_picture")}),
        ("Gamification", {"fields": ("xp", "level")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "username", "password1", "password2")}),)
    search_fields = ("email", "username")

    actions = ["make_admin", "remove_admin", "suspend_accounts", "reactivate_accounts"]

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
admin.site.register(VerificationCode)
