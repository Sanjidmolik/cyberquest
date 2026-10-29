"""Reports, automatic-warning metadata, restrictions and the append-only moderation log.

Privacy rules:
- Moderators read message text ONLY for messages a participant reported: the report keeps an
  encrypted snapshot of that message and up to three messages before and after it. Every
  time a moderator opens it, a "viewed content" entry is written to the log.
- Automatic keyword checks never store or show text: a FlagEvent only records that the
  sender was warned, and whether they sent anyway.
- Nothing here punishes automatically. Restrictions are only created by a moderator.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class FlagEvent(models.Model):
    """The sender saw "this message may be offensive" (no text, no matched words)."""
    WARNED, SENT_ANYWAY = "warned", "sent_anyway"
    KINDS = [(WARNED, "Warned before sending"), (SENT_ANYWAY, "Sent anyway after a warning")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=12, choices=KINDS)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class Report(models.Model):
    REASONS = [
        ("harassment", "Harassment or bullying"), ("hate", "Hate"), ("threats", "Threats"),
        ("spam", "Spam"), ("sexual", "Sexual content"), ("other", "Something else"),
    ]
    OPEN, RESOLVED = "open", "resolved"
    STATUSES = [(OPEN, "Open"), (RESOLVED, "Resolved")]

    message = models.ForeignKey("messaging.Message", on_delete=models.SET_NULL, null=True, related_name="+")
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    reported_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                      related_name="+")
    reason = models.CharField(max_length=12, choices=REASONS)
    note = models.TextField(blank=True)          # the reporter's note, encrypted like messages
    # Encrypted JSON: the reported message and up to 3 messages before and after it, taken when
    # the report was made (so it survives the sender deleting their account).
    snapshot = models.TextField()
    status = models.CharField(max_length=10, choices=STATUSES, default=OPEN, db_index=True)
    resolution = models.CharField(max_length=12, blank=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]
        permissions = [("moderate", "Can review reports and restrict messaging")]
        constraints = [models.UniqueConstraint(fields=["message", "reporter"], name="report_message_once")]

    def __str__(self):
        return f"report {self.pk} ({self.reason}, {self.status})"


class RestrictionQuerySet(models.QuerySet):
    def active(self, now=None):
        now = now or timezone.now()
        return self.filter(kind__in=[Restriction.MUTE, Restriction.SUSPENSION], lifted_at__isnull=True).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now))


class Restriction(models.Model):
    """A moderator's decision about a user's messaging. Mutes end on their own at `ends_at`."""
    WARNING, MUTE, SUSPENSION = "warning", "mute", "suspension"
    KINDS = [(WARNING, "Warning"), (MUTE, "Messaging muted"), (SUSPENSION, "Messaging suspended")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="messaging_restrictions")
    kind = models.CharField(max_length=12, choices=KINDS)
    reason = models.TextField()
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)        # mutes only
    lifted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    report = models.ForeignKey(Report, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    objects = RestrictionQuerySet.as_manager()

    class Meta:
        ordering = ["-starts_at"]

    def __str__(self):
        return f"{self.get_kind_display()} for {self.user_id}"


class AppendOnly(Exception):
    pass


class LogQuerySet(models.QuerySet):
    def delete(self):
        raise AppendOnly("The moderation log can't be deleted.")


class ModerationLog(models.Model):
    """Append-only: who did what, when and why. Entries can't be edited or deleted through the
    app; the retention job only anonymises them (the reason text and report link) after 180
    days, and a deleted account leaves its entries with the user reference cleared."""
    ACTIONS = [
        ("view", "Viewed reported content"), ("dismiss", "Dismissed"), ("warn", "Warned"),
        ("mute_24h", "Muted messaging for 24 hours"), ("mute_7d", "Muted messaging for 7 days"),
        ("suspend", "Suspended messaging"), ("lift", "Lifted a restriction"),
    ]
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    subject = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    report = models.ForeignKey(Report, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    action = models.CharField(max_length=10, choices=ACTIONS)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = LogQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-pk"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise AppendOnly("The moderation log can't be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnly("The moderation log can't be deleted.")
