from django.conf import settings
from django.db import models


class CareerRoadmap(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="career_roadmap",
    )
    subject = models.CharField(max_length=120)
    skills = models.JSONField(default=list)
    interests = models.TextField(blank=True)
    experience = models.TextField(blank=True)
    study_hours = models.PositiveSmallIntegerField(default=5)
    career_role = models.CharField(max_length=120, blank=True)
    skill_gaps = models.JSONField(default=list)
    learning_roadmap = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user_id} → {self.career_role or '(pending)'}"
