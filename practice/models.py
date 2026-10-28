from django.conf import settings
from django.db import models


class PracticeSession(models.Model):
    """One practice attempt: simulation or incident. Stores decisions + result."""

    DOMAIN_CHOICES = [
        ("phishing", "Phishing"),
        ("password", "Password Security"),
        ("network", "Network Defense"),
        ("cryptography", "Cryptography"),
        ("steganography", "Steganography"),
        ("osint", "OSINT Investigation"),
        ("safety", "Online Safety"),
        ("malware", "Malware & Ransomware Defence"),
        ("device", "Device & Data Protection"),
        ("privacy", "Social Media & Privacy"),
        ("response", "Attack Response & Recovery"),
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


# ---- Interactive practice sessions (step engine) ----
# Scenario content lives in practice/scenario_content/*.json and is loaded with
# `manage.py load_scenarios`. Answers stay on the server: see practice/graders.py.

class Scenario(models.Model):
    KIND = [("simulation", "Simulation"), ("incident", "Incident"), ("choice", "Choice")]

    slug = models.SlugField(unique=True)
    # The course this scenario practises. CyberQuest has no separate module model,
    # so the topic is the Course itself (matched by Course.code when loading).
    topic = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="practice_scenarios")
    kind = models.CharField(max_length=12, choices=KIND)
    title = models.CharField(max_length=160)
    difficulty = models.CharField(max_length=12)
    est_minutes = models.PositiveSmallIntegerField()
    # Kept for the data format, but Practice is self-paced: the engine never shows a countdown.
    time_limit_sec = models.PositiveIntegerField(null=True, blank=True)
    xp_reward = models.PositiveIntegerField()
    content = models.JSONField()  # steps including answers; never sent to the browser as-is
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["topic__order", "slug"]

    def __str__(self):
        return self.slug


class Attempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="practice_attempts")
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="attempts")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    hearts = models.PositiveSmallIntegerField(default=3)
    score = models.IntegerField(default=0)
    state = models.JSONField(default=dict, blank=True)  # branch meters, current scene, results
    outcome = models.CharField(max_length=20, blank=True)
    xp_awarded = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["user", "scenario"])]

    def __str__(self):
        return f"{self.user_id} {self.scenario_id} {self.outcome or 'in progress'}"


class StepAnswer(models.Model):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="answers")
    step_index = models.PositiveSmallIntegerField()
    answer = models.JSONField()
    correct = models.BooleanField(null=True)
    time_ms = models.PositiveIntegerField(default=0)
    confidence = models.CharField(max_length=12, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["attempt", "step_index", "pk"]
