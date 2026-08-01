"""
courses/admin.py
--------------------
This is where an admin actually WRITES the course content -- via
/admin/ -> Courses -> click a course -> edit the "Content" field.
No code changes are needed to add, edit, or reorder lessons.
"""

from django.contrib import admin
from .models import Course, CourseProgress


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "order", "is_published")
    list_editable = ("order", "is_published")  # quick reordering right from the list page
    ordering = ("order",)
    search_fields = ("code", "title")
    fieldsets = (
        (None, {"fields": ("code", "title", "short_description", "order", "is_published")}),
        ("Lesson Content", {"fields": ("content",)}),
    )


@admin.register(CourseProgress)
class CourseProgressAdmin(admin.ModelAdmin):
    """Read-only view of who has completed which course, and when."""
    list_display = ("user", "course", "completed_at")
    list_filter = ("course",)
    search_fields = ("user__email", "user__username")
    ordering = ("-completed_at",)
