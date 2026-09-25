from django.conf import settings
from django.db import models


class PracticeSession(models.Model):
    """One practice attempt: simulation or incident. Stores decisions + result."""

    DOMAIN_CHOICES = [
        ("phishing", "Phishing"),
        ("password", "Password Security"),
        ("network", "Network Defense"),
        ("cryptography", "Cryptography"),
        ("osint", "OSINT Investigation"),
    ]
    ACTIVITY_CHOICES = [
        ("game", "Game"),
        ("simulation", "Simulation"),
        ("incident", "Incident"),
    ]
    DIFFICULTY_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]
    STATUS_CHOICES = [
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="practice_sessions",
    )
    domain = models.CharField(max_length=20, choices=DOMAIN_CHOICES)
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_CHOICES)
    scenario_key = models.CharField(max_length=80)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES)
    score = models.IntegerField(default=0)
    max_score = models.PositiveIntegerField(default=100)
    decisions = models.JSONField(default=list, blank=True)
    state = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="in_progress")
    result_summary = models.TextField(blank=True)
    strengths = models.TextField(blank=True)
    improvements = models.TextField(blank=True)
    xp_awarded = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id} {self.domain} {self.activity_type} {self.score}%"

    @property
    def percent(self):
        if not self.max_score:
            return 0
        return max(0, min(100, round(self.score / self.max_score * 100)))
