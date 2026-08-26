"""
courses/models.py
--------------------
Course content is managed by ADMINS through the Django admin panel.

Two ways an admin can provide a course's content:
  1. Type plain text into `content` (existing behavior) -- the reader
     will auto-paginate this into flippable "pages" client-side.
  2. Upload a PDF into `pdf_file` -- the reader renders the PDF's own
     pages directly as the flippable pages instead (via PDF.js).
If both are set, the PDF takes priority (it's the richer e-book format).
"""

from django.conf import settings
from django.db import models


class Course(models.Model):
    code = models.CharField(max_length=20, unique=True,
        help_text="Short identifier shown in the UI, e.g. MOD-01")
    title = models.CharField(max_length=150)
    short_description = models.CharField(max_length=250,
        help_text="One-line summary shown on the course list page.")
    content = models.TextField(
        blank=True,
        help_text="Plain-text lesson content. Used ONLY if no PDF e-book is uploaded below. "
                   "The reader automatically splits this into flippable pages.",
    )
    pdf_file = models.FileField(
        upload_to="course_ebooks/", blank=True, null=True,
        help_text="Optional: upload a PDF e-book for this course instead of typing plain text. "
                   "If uploaded, this takes priority over the Content field above, and the "
                   "reader displays the PDF's actual pages with a page-flip effect.",
    )
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "code"]

    def __str__(self):
        return f"{self.code}: {self.title}"

    def uses_pdf(self) -> bool:
        return bool(self.pdf_file)


class CourseProgress(models.Model):
    """Records that a user has FINISHED reading a course (reached the last page)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_progress")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="progress_records")
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "course")

    def __str__(self):
        return f"{self.user.email} completed {self.course.code}"


class ReadingProgress(models.Model):
    """
    Tracks WHERE a user currently is in a course they haven't finished yet
    (which page they last had open), so they can resume instead of
    starting over from page 1 -- a small thing, but it's exactly the kind
    of friction that makes people abandon reading.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reading_progress")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="reading_progress")
    last_page_index = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "course")
