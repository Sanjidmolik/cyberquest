from django.conf import settings
from django.db import models


class Notification(models.Model):
    """A single notification for one user (e.g. 'You earned a badge!')."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=255)
    link_url = models.CharField(max_length=200, blank=True, help_text="Optional URL to send the user to when clicked.")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email}: {self.message[:40]}"
