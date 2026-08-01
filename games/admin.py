"""
games/admin.py
------------------
Lets you view every game attempt (score, XP awarded, timestamp) per user
in the Django admin panel, at http://127.0.0.1:8000/admin/
"""

from django.contrib import admin
from .models import GameAttempt


@admin.register(GameAttempt)
class GameAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "game_key", "score", "total_questions", "xp_awarded", "completed_at")
    list_filter = ("game_key",)
    search_fields = ("user__email", "user__username")
    ordering = ("-completed_at",)
