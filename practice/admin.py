from django.contrib import admin
from .models import Attempt, PracticeSession, Scenario, StepAnswer


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
    list_display = ("slug", "title", "topic", "kind", "difficulty", "xp_reward", "version")
    list_filter = ("kind", "difficulty", "topic")
    search_fields = ("slug", "title")


class StepAnswerInline(admin.TabularInline):
    model = StepAnswer
    extra = 0
    readonly_fields = ("step_index", "answer", "correct", "time_ms", "confidence", "created_at")
    can_delete = False


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "scenario", "started_at", "finished_at", "hearts", "score", "outcome", "xp_awarded")
    list_filter = ("scenario", "outcome")
    search_fields = ("user__email", "scenario__slug")
    readonly_fields = ("started_at", "finished_at")
    inlines = [StepAnswerInline]
