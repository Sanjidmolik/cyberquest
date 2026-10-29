"""Read-only views for superusers. Reported text stays encrypted here; moderators read it in
the moderation panel, where every view is logged."""

from django.contrib import admin

from .models import FlagEvent, ModerationLog, Report, Restriction


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Report)
class ReportAdmin(ReadOnly):
    list_display = ("pk", "reason", "status", "resolution", "created_at", "resolved_at")
    list_filter = ("status", "reason")
    exclude = ("snapshot", "note")


@admin.register(Restriction)
class RestrictionAdmin(ReadOnly):
    list_display = ("user", "kind", "starts_at", "ends_at", "lifted_at")
    list_filter = ("kind",)


@admin.register(ModerationLog)
class ModerationLogAdmin(ReadOnly):
    list_display = ("created_at", "actor", "action", "subject", "report")
    list_filter = ("action",)


@admin.register(FlagEvent)
class FlagEventAdmin(ReadOnly):
    list_display = ("created_at", "user", "kind")
    list_filter = ("kind",)
