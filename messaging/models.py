"""One-to-one messaging: conversations, encrypted messages, who-can-message settings, blocks.

Message bodies are stored encrypted (messaging/crypto.py). This is encryption at rest, not
end-to-end: the server holds the key, so moderators can review reported messages.

Disappearing messages (v2): a message with `expires_at` in the past is gone. The default
manager never returns it, so no page, API, export or snapshot can serve it even before
`purge_expired_messages` deletes the row.
"""

import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from . import crypto
from .storage import private_storage

# Disappearing-message timers: key -> (label, seconds after sending, or None).
OFF, AFTER_VIEW = "off", "view"
TIMERS = {
    OFF: ("Off", None),
    AFTER_VIEW: ("After viewing", None),
    "1h": ("1 hour", 3600),
    "24h": ("24 hours", 86400),
    "7d": ("7 days", 7 * 86400),
}
TIMER_CHOICES = [(key, label) for key, (label, _) in TIMERS.items()]
VIEW_GRACE = timedelta(seconds=30)   # "after viewing": gone 30 s after the recipient reads it
REPORT_HOLD = timedelta(hours=1)     # an opened view-once photo stays reportable this long


def expiry_for(timer, sent_at):
    seconds = TIMERS.get(timer, (None, None))[1]
    return sent_at + timedelta(seconds=seconds) if seconds else None


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
    # The last message id each side's client has fetched ("delivered").
    a_delivered_upto = models.PositiveBigIntegerField(default=0)
    b_delivered_upto = models.PositiveBigIntegerField(default=0)
    # Applies to messages sent after it was set.
    disappear_after = models.CharField(max_length=4, choices=TIMER_CHOICES, default=OFF)

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

    def delivered_upto(self, user):
        return self.a_delivered_upto if self.user_a_id == user.pk else self.b_delivered_upto


class VisibleMessageManager(models.Manager):
    """Only messages that haven't expired. This is the default manager, so related managers
    (`conversation.messages`) and every query built on `Message.objects` hide expired rows."""

    def get_queryset(self):
        return super().get_queryset().filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))


class Message(models.Model):
    TEXT, SYSTEM, PHOTO = "text", "system", "photo"
    KINDS = [(TEXT, "Text"), (SYSTEM, "System notice"), (PHOTO, "View-once photo")]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    body = models.TextField()                     # Fernet token, never plain text
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    removed = models.BooleanField(default=False)  # the sender deleted their account: text removed
    kind = models.CharField(max_length=6, choices=KINDS, default=TEXT)
    timer = models.CharField(max_length=4, choices=TIMER_CHOICES, default=OFF)   # the chat's timer when sent
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # View-once photo: Fernet-encrypted bytes in private storage; deleted when opened.
    photo = models.FileField(storage=private_storage, upload_to="msg-photos/", blank=True, max_length=200)
    photo_opened_at = models.DateTimeField(null=True, blank=True)
    # After opening: an encrypted copy kept REPORT_HOLD so the recipient can still report it.
    # No view ever reads this field; only the report action moves it into the report.
    report_copy = models.FileField(storage=private_storage, upload_to="msg-report-hold/", blank=True, max_length=200)
    report_copy_until = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = VisibleMessageManager()
    all_objects = models.Manager()               # cleanup job and admin only

    class Meta:
        base_manager_name = "all_objects"
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
    # Reciprocal: turning either off also hides other people's.
    read_receipts = models.BooleanField(default=True)
    show_online = models.BooleanField(default=True)
    default_timer = models.CharField(max_length=4, choices=TIMER_CHOICES, default=OFF)
    last_seen_at = models.DateTimeField(null=True, blank=True)   # presence heartbeat (throttled)

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
