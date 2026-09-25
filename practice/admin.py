from django.contrib import admin
from .models import PracticeSession


@admin.register(PracticeSession)
class PracticeSessionAdmin(admin.ModelAdmin):
    list_display = (
        "user", "domain", "activity_type", "scenario_key",
        "difficulty", "score", "status", "xp_awarded", "created_at",
    )
    list_filter = ("domain", "activity_type", "difficulty", "status")
    search_fields = ("user__email", "scenario_key")
    readonly_fields = ("created_at", "completed_at")
