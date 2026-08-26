from django.contrib import admin
from .models import GameAttempt


@admin.register(GameAttempt)
class GameAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "game_key", "score", "total_questions", "xp_awarded", "completed_at")
    list_filter = ("game_key",)
