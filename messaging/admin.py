"""Metadata only: message text is never shown in the admin. Reported messages are reviewed
in the moderation panel, one message and its nearest context at a time."""

from django.contrib import admin

from .models import Block, Conversation


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("public_id", "state", "created_at", "last_message_at")
    list_filter = ("state",)
    readonly_fields = ("public_id", "user_a", "user_b", "initiator", "state", "created_at", "last_message_at")
    exclude = ("a_read_upto", "b_read_upto")

    def has_add_permission(self, request):
        return False


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("blocker", "blocked", "created_at")
    readonly_fields = ("blocker", "blocked", "created_at")

    def has_add_permission(self, request):
        return False
