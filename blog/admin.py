from django.contrib import admin

from .models import Post, PostImage


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    """Read-only overview; posts are written in the Command Center blog editor."""
    list_display = ("title", "slug", "status", "published_at", "author", "updated_at")
    list_filter = ("status",)
    search_fields = ("title", "slug")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PostImage)
class PostImageAdmin(admin.ModelAdmin):
    list_display = ("alt", "post", "width", "height", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
