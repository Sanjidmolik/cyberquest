"""One-to-one messaging: conversations, encrypted messages, who-can-message settings, blocks.

Message bodies are stored encrypted (messaging/crypto.py). This is encryption at rest, not
end-to-end: the server holds the key, so moderators can review reported messages.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from . import crypto


class ConversationQuerySet(models.QuerySet):
    def involving(self, user):
        return self.filter(Q(user_a=user) | Q(user_b=user))


class Conversation(models.Model):
    """Exactly two people. `user_a` has the lower id, so each pair has one conversation."""

    PENDING, ACCEPTED, DECLINED = "pending", "accepted", "declined"
    STATES = [(PENDING, "Request"), (ACCEPTED, "Accepted"), (DECLINED, "Declined")]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # SET_NULL: when one person deletes their account, the other keeps the conversation,
    # with that person's messages shown as "Deleted user" and their text removed.
    user_a = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    user_b = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    initiator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    state = models.CharField(max_length=10, choices=STATES, default=PENDING)
    created_at = models.DateTimeField(default=timezone.now)
    last_message_at = models.DateTimeField(default=timezone.now, db_index=True)
    # The last message id each side has seen (unread = newer messages from the other side).
    a_read_upto = models.PositiveBigIntegerField(default=0)
    b_read_upto = models.PositiveBigIntegerField(default=0)

    objects = ConversationQuerySet.as_manager()

    class Meta:
        ordering = ["-last_message_at"]
        constraints = [models.UniqueConstraint(fields=["user_a", "user_b"], name="one_conversation_per_pair")]

    def __str__(self):
        return str(self.public_id)

    @staticmethod
    def pair(one, two):
        return (one, two) if one.pk < two.pk else (two, one)

    def is_participant(self, user):
        return user.pk is not None and user.pk in (self.user_a_id, self.user_b_id)

    def other(self, user):
        return self.user_b if self.user_a_id == user.pk else self.user_a

    def read_upto(self, user):
        return self.a_read_upto if self.user_a_id == user.pk else self.b_read_upto

    def is_request_for(self, user):
        return self.state == self.PENDING and self.initiator_id != user.pk


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    body = models.TextField()                     # Fernet token, never plain text
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    removed = models.BooleanField(default=False)  # the sender deleted their account: text removed

    class Meta:
        ordering = ["pk"]
        indexes = [models.Index(fields=["conversation", "id"])]

    def __str__(self):
        return f"{self.conversation_id}:{self.pk}"

    @property
    def text(self):
        return "" if self.removed or not self.body else crypto.decrypt(self.body)

    def set_text(self, text):
        self.body = crypto.encrypt(text)


class MessagingPreference(models.Model):
    EVERYONE, NOBODY = "everyone", "nobody"
    CHOICES = [(EVERYONE, "Everyone"), (NOBODY, "Nobody")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True,
                                related_name="messaging_preference")
    who_can_message = models.CharField(max_length=10, choices=CHOICES, default=EVERYONE)

    def __str__(self):
        return f"{self.user_id}: {self.who_can_message}"


class Block(models.Model):
    blocker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    blocked = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["blocker", "blocked"], name="block_once")]

    def __str__(self):
        return f"{self.blocker_id} blocks {self.blocked_id}"
