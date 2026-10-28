from django.contrib import admin
from .models import (
    Chapter, ChapterQuestion, ComicPanel, Course, CourseProgress, ReadingProgress,
)


class ChapterInline(admin.TabularInline):
    model = Chapter
    extra = 0
    fields = ("order", "title")
    show_change_link = True


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "order", "is_published", "is_coming_soon", "content_source")
    list_editable = ("order", "is_published", "is_coming_soon")
    list_filter = ("is_published", "is_coming_soon")
    ordering = ("order",)
    search_fields = ("code", "title")
    inlines = [ChapterInline]
    fieldsets = (
        (None, {"fields": ("code", "title", "short_description", "summary", "thumbnail", "order",
                           "is_published", "is_coming_soon")}),
        ("Content — choose ONE", {
            "fields": ("pdf_file", "content"),
            "description": "Upload a PDF e-book, add comic chapters below, OR type plain text. "
                            "A PDF wins over chapters, and chapters win over plain text.",
        }),
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # Phase 1 — Step 5: link current files through the protected views, never a bucket URL.
        from certificates.admin import ProtectedFileWidget

        if db_field.name == "pdf_file":
            kwargs["widget"] = ProtectedFileWidget("courses:ebook", arg_attr="code")
        elif db_field.name == "thumbnail":
            kwargs["widget"] = ProtectedFileWidget("courses:thumbnail", arg_attr="code")
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="Content type")
    def content_source(self, obj):
        if obj.uses_pdf():
            return "📕 PDF e-book"
        return "💬 Comic chapters" if obj.has_chapters else "📝 Plain text"


class ComicPanelInline(admin.TabularInline):
    model = ComicPanel
    extra = 0
    fields = ("order", "caption", "speech_bubble", "background_color", "bubble_align")


class ChapterQuestionInline(admin.StackedInline):
    model = ChapterQuestion
    extra = 0
    fields = ("order", "prompt", "options", "correct_index", "explanation")


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ("course", "order", "title")
    list_filter = ("course",)
    ordering = ("course__order", "order")
    inlines = [ComicPanelInline, ChapterQuestionInline]


@admin.register(CourseProgress)
class CourseProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "completed_at")
    list_filter = ("course",)
    search_fields = ("user__email", "user__username")


@admin.register(ReadingProgress)
class ReadingProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "last_page_index", "updated_at")
    search_fields = ("user__email",)
