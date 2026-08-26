"""
achievements/models.py
--------------------------
Badge = a definition of an achievement, managed by admins (like courses).
UserBadge = a record that a specific user actually earned a specific badge.

The CONDITIONS for earning each badge live in achievements/checks.py, not
here -- this file only defines what a badge IS, not when it's awarded.
"""

from django.conf import settings
from django.db import models


class Badge(models.Model):
    """One achievement definition, e.g. 'Phishing Expert'."""

    code = models.CharField(
        max_length=50, unique=True,
        help_text="Internal identifier used by the awarding logic, e.g. 'phishing_expert'. "
                   "Must match a check in achievements/checks.py to ever be awarded.",
    )
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=250)
    icon_emoji = models.CharField(max_length=10, default="🏆")
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive badges are hidden and can no longer be newly earned.",
    )

    def __str__(self):
        return f"{self.icon_emoji} {self.name}"


class UserBadge(models.Model):
    """Records that a specific user has earned a specific badge."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="badges")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="awarded_to")
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "badge")  # can't earn the same badge twice

    def __str__(self):
        return f"{self.user.email} earned {self.badge.name}"
