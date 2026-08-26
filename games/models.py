from django.conf import settings
from django.db import models


class GameAttempt(models.Model):
    GAME_CHOICES = [
        ("phishing_simulator", "Phishing Simulator"),
        ("password_cracker", "Password Cracker Challenge"),
        ("whack_a_phish", "Whack-a-Phish"),
        ("network_defense", "Network Defense"),
        ("cryptography", "Cryptography Challenge"),
        ("osint", "OSINT Investigation"),
        ("steganography", "Steganography Hunt"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="game_attempts")
    game_key = models.CharField(max_length=50, choices=GAME_CHOICES)
    score = models.PositiveIntegerField()
    total_questions = models.PositiveIntegerField()
    xp_awarded = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.game_key} - {self.score}/{self.total_questions}"
