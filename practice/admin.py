from django.contrib import admin
from .models import Attempt, PracticeSession, Scenario, ScenarioVersion, StepAnswer, StudioAuditLog


@admin.register(PracticeSession)
class PracticeSessionAdmin(admin.ModelAdmin):
    list_display = (
        "user", "domain", "activity_type", "scenario_key",
        "difficulty", "score", "status", "xp_awarded", "created_at",
    )
    list_filter = ("domain", "activity_type", "difficulty", "status")
    search_fields = ("user__email", "scenario_key")
    readonly_fields = ("created_at", "completed_at")


@admin.register(Scenario)
class ScenarioAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "topic", "kind", "status", "source", "difficulty", "xp_reward", "version", "updated_at")
    list_filter = ("status", "source", "kind", "difficulty", "topic")
    search_fields = ("slug", "title")
    readonly_fields = ("content_hash", "created_by", "updated_by", "created_at", "updated_at")


class _ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ScenarioVersion)
class ScenarioVersionAdmin(_ReadOnlyAdmin):
    list_display = ("scenario", "version", "published_by", "published_at")
    list_filter = ("scenario",)


@admin.register(StudioAuditLog)
class StudioAuditLogAdmin(_ReadOnlyAdmin):
    list_display = ("created_at", "user", "slug", "action", "version", "summary")
    list_filter = ("action",)
    search_fields = ("slug", "user__email", "summary")


class StepAnswerInline(admin.TabularInline):
    model = StepAnswer
    extra = 0
    readonly_fields = ("step_index", "answer", "correct", "time_ms", "confidence", "created_at")
    can_delete = False


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "scenario", "started_at", "finished_at", "hearts", "score", "outcome", "xp_awarded", "is_preview")
    list_filter = ("is_preview", "scenario", "outcome")
    search_fields = ("user__email", "scenario__slug")
    readonly_fields = ("started_at", "finished_at")
    inlines = [StepAnswerInline]
