"""
courses/models.py
--------------------
Course content is managed by ADMINS through the Django admin panel.

Three ways a course can provide its content:
  1. Upload a PDF into `pdf_file` -- the reader renders the PDF's own
     pages directly as the flippable pages (via PDF.js).
  2. Comic chapters (Chapter + ComicPanel + ChapterQuestion). The core
     defence curriculum is seeded by `manage.py sync_curriculum`.
  3. Type plain text into `content` (existing behavior) -- the reader
     will auto-paginate this into flippable "pages" client-side.
The first one present wins: PDF, then chapters, then plain text. So an
existing PDF course (Phishing) keeps showing exactly its PDF.

A Coming Soon course (`is_coming_soon`) stays on the shelf as a locked card.
Students cannot open it, and it never counts toward progress or unlocks.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.core.files.uploadedfile import UploadedFile
from django.db import models
from django.utils.functional import cached_property

THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024
THUMBNAIL_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
# Phase 1 — Step 7: server-side cap for course e-books (every upload path).
EBOOK_MAX_BYTES = 25 * 1024 * 1024


def validate_course_ebook(upload):
    """Reject e-books over 25 MB. Runs for the Command Center form and Django admin.

    Model validation sees a FieldFile wrapping the new upload (not yet
    committed to storage), so both shapes are checked. Files already in
    storage are left alone.
    """
    if not upload:
        return
    is_new = isinstance(upload, UploadedFile) or getattr(upload, "_committed", True) is False
    if not is_new:
        return
    if (upload.size or 0) > EBOOK_MAX_BYTES:
        raise ValidationError("PDF must be 25 MB or smaller.")


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


HEX_COLOR = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Use a hex colour like #FFC21A.")


class CourseQuerySet(models.QuerySet):
    def active(self):
        """Courses students can open. Coming Soon books never count toward progress."""
        return self.filter(is_published=True, is_coming_soon=False)

    def coming_soon(self):
        """Published but locked: shown on the shelf, never opened by students."""
        return self.filter(is_published=True, is_coming_soon=True)


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
        validators=[validate_course_ebook],
        help_text="Optional: upload a PDF e-book (up to 25 MB) for this course instead of typing plain text. "
                   "If uploaded, this takes priority over the Content field above, and the "
                   "reader displays the PDF's actual pages with a page-flip effect.",
    )
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)
    is_coming_soon = models.BooleanField(
        default=False,
        help_text="Shown on the shelf but cannot be opened, and does not count toward unlocking games.",
    )
    summary = models.TextField(
        blank=True,
        help_text="Longer blurb shown on the reading stand. Falls back to the short description.",
    )
    cover_image = models.CharField(
        max_length=200, blank=True,
        help_text="Static path of the comic cover, e.g. courses/covers/cover_01_phishing.svg. "
                  "Falls back to the uploaded thumbnail.",
    )
    accent_color = models.CharField(max_length=7, default="#FFC21A", validators=[HEX_COLOR],
        help_text="Hex colour of the cover strip, e.g. #FF8FAB.")
    spine_color = models.CharField(max_length=7, default="#35097E", validators=[HEX_COLOR],
        help_text="Hex colour of the book spine.")

    objects = CourseQuerySet.as_manager()

    class Meta:
        ordering = ["order", "code"]

    def __str__(self):
        return f"{self.code}: {self.title}"

    def uses_pdf(self) -> bool:
        return bool(self.pdf_file)

    @cached_property
    def has_chapters(self) -> bool:
        """Comic chapters are read when no PDF is uploaded (a PDF always wins)."""
        return not self.uses_pdf() and self.chapters.exists()

    def is_open_to(self, user) -> bool:
        """Students open published, non-Coming-Soon courses. Admins may preview anything."""
        if user.is_authenticated and (user.is_superuser or user.is_staff):
            return True
        return self.is_published and not self.is_coming_soon

    def clean(self):
        super().clean()
        try:
            validate_course_thumbnail(self.thumbnail)
        except ValidationError as exc:
            raise ValidationError({"thumbnail": exc.messages})

    def safe_thumbnail_url(self):
        from django.urls import reverse

        from cyberquest.media_access import file_exists

        # Cached for remote storage: this runs once per course card.
        if not file_exists(self.thumbnail, cache_seconds=600):
            return ""
        return reverse("courses:thumbnail", args=[self.code])


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


class Chapter(models.Model):
    """One comic chapter of a course. Chapters replace the plain-text/PDF body when present."""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="chapters")
    order = models.PositiveIntegerField(default=0)
    title = models.CharField(max_length=150)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.course.code} · {self.title}"


class ComicPanel(models.Model):
    """A comic beat: `caption` names the speaker (or a narration label), `speech_bubble` is the line."""
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="panels")
    order = models.PositiveIntegerField(default=0)
    caption = models.CharField(max_length=200, blank=True)
    speech_bubble = models.CharField(max_length=300, blank=True)
    background_color = models.CharField(max_length=7, default="#FFE7A8", validators=[HEX_COLOR])
    span = models.PositiveSmallIntegerField(choices=[(1, "1 column"), (2, "2 columns")], default=1)
    bubble_align = models.CharField(max_length=5, choices=[("left", "Left"), ("right", "Right")], default="left")

    class Meta:
        ordering = ["order", "id"]

    NARRATION_CAPTIONS = {"narrator", "story", "meanwhile", "later"}

    @property
    def kind(self) -> str:
        """How the reader draws the panel: a story caption box, a defence activity, or a speech bubble."""
        caption = (self.caption or "").strip().lower()
        if not caption or caption in self.NARRATION_CAPTIONS:
            return "narration"
        if caption.startswith("defence activity"):
            return "activity"
        return "speech"


class ChapterQuestion(models.Model):
    """Knowledge-check question at the end of a chapter. Options are one per line."""
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveIntegerField(default=0)
    prompt = models.CharField(max_length=300)
    options = models.TextField(help_text="One answer option per line.")
    correct_index = models.PositiveSmallIntegerField(help_text="0 for the first option, 1 for the second, ...")
    explanation = models.TextField()

    class Meta:
        ordering = ["order", "id"]

    def option_list(self):
        return [line.strip() for line in self.options.splitlines() if line.strip()]

    def correct_option(self):
        options = self.option_list()
        return options[self.correct_index] if self.correct_index < len(options) else ""

    def clean(self):
        super().clean()
        if self.correct_index >= len(self.option_list()):
            raise ValidationError({"correct_index": "Pick one of the listed options."})


class ChapterProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chapter_progress")
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="progress_records")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "chapter")
