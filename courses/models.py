"""
courses/models.py
--------------------
Course content is now managed by ADMINS through the Django admin panel,
instead of being hardcoded text inside views.py. This means an admin can
add, edit, reorder, or remove course modules without touching any code.
"""

from django.conf import settings
from django.db import models


class Course(models.Model):
    """One learning module (e.g. 'Phishing & Social Engineering')."""

    code = models.CharField(
        max_length=20, unique=True,
        help_text="Short identifier shown in the UI, e.g. MOD-01",
    )
    title = models.CharField(max_length=150)
    short_description = models.CharField(
        max_length=250,
        help_text="One-line summary shown on the course list page.",
    )
    content = models.TextField(
        help_text="The full lesson content shown on the course's reading page. "
                   "Plain text/paragraphs -- line breaks are preserved automatically.",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Controls display order on the course list page (lowest first).",
    )
    is_published = models.BooleanField(
        default=True,
        help_text="Unpublished courses are hidden from users but kept in the admin panel.",
    )

    class Meta:
        ordering = ["order", "code"]

    def __str__(self):
        return f"{self.code}: {self.title}"


class CourseProgress(models.Model):
    """Tracks that a specific user has read/completed a specific course."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_progress"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="progress_records"
    )
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "course")  # one completion record per user per course

    def __str__(self):
        return f"{self.user.email} completed {self.course.code}"
