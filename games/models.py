"""
games/models.py
------------------
Tracks completed game attempts, so we know:
  - whether a user has already earned XP for a given game (prevents
    infinite XP farming by replaying the same game)
  - basic stats for the admin panel (score, timestamp)
"""

from django.conf import settings
from django.db import models


class GameAttempt(models.Model):
    """One record per user per game completion."""

    GAME_CHOICES = [
        ("phishing_simulator", "Phishing Simulator"),
        ("password_cracker", "Password Cracker Challenge"),
        ("network_defense", "Network Defense"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="game_attempts"
    )
    game_key = models.CharField(max_length=50, choices=GAME_CHOICES)
    score = models.PositiveIntegerField(default=0)       # correct answers
    total_questions = models.PositiveIntegerField(default=0)
    xp_awarded = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # A user can retry a game, but we only award XP the FIRST time,
        # enforced in the view logic (not here) so retries are still allowed.
        ordering = ["-completed_at"]

    def __str__(self):
        return f"{self.user.email} - {self.get_game_key_display()} ({self.score}/{self.total_questions})"
