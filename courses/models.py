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
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import models

THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024
THUMBNAIL_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


def validate_course_thumbnail(image):
    """Accept only real raster images. Extension and Content-Type are not proof."""
    if not image or not isinstance(image, UploadedFile):
        return
    if getattr(image, "size", 0) > THUMBNAIL_MAX_BYTES:
        raise ValidationError("Image must be 2 MB or smaller.")
    try:
        from PIL import Image

        image.seek(0)
        with Image.open(image) as img:
            img.verify()
        image.seek(0)
        with Image.open(image) as img:
            img.load()
            if img.format not in THUMBNAIL_FORMATS:
                raise ValidationError("Upload a JPG, PNG, WEBP, or GIF image.")
        image.seek(0)
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("Upload a JPG, PNG, WEBP, or GIF image.")


class Course(models.Model):
    code = models.CharField(max_length=20, unique=True,
        help_text="Short identifier shown in the UI, e.g. MOD-01")
    title = models.CharField(max_length=150)
    short_description = models.CharField(max_length=250,
        help_text="One-line summary shown on the course list page.")
    thumbnail = models.ImageField(
        upload_to="course_thumbnails/",
        blank=True,
        null=True,
        help_text="Optional cover image shown on course cards (JPG, PNG, WEBP, or GIF, up to 2 MB).",
    )
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

    def clean(self):
        super().clean()
        try:
            validate_course_thumbnail(self.thumbnail)
        except ValidationError as exc:
            raise ValidationError({"thumbnail": exc.messages})

    def safe_thumbnail_url(self):
        field = self.thumbnail
        if not field or not getattr(field, "name", ""):
            return ""
        try:
            if not field.storage.exists(field.name):
                return ""
            return field.url
        except Exception:
            return ""


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
