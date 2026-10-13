from django.contrib import admin
from .models import Course, CourseProgress, ReadingProgress


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "order", "is_published", "content_source")
    list_editable = ("order", "is_published")
    ordering = ("order",)
    search_fields = ("code", "title")
    fieldsets = (
        (None, {"fields": ("code", "title", "short_description", "thumbnail", "order", "is_published")}),
        ("Content — choose ONE", {
            "fields": ("pdf_file", "content"),
            "description": "Upload a PDF e-book OR type plain text below. "
                            "If a PDF is uploaded, it takes priority and the plain text is ignored.",
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
        return "📕 PDF e-book" if obj.uses_pdf() else "📝 Plain text"


@admin.register(CourseProgress)
class CourseProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "completed_at")
    list_filter = ("course",)
    search_fields = ("user__email", "user__username")


@admin.register(ReadingProgress)
class ReadingProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "last_page_index", "updated_at")
    search_fields = ("user__email",)
