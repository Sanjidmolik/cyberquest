"""Messaging actions. Views and the API call these; each one checks the rules in policy.py."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Case, Count, F, OuterRef, Q, Subquery, When
from django.utils import timezone

from accounts.public import avatar_url, default_avatar_url

from . import events, policy
from .models import Block, Conversation, Message, MessagingPreference
from .policy import Denied, NeedsConfirmation

PREVIEW_LENGTH = 80
PAGE = 50


def clean_text(text):
    text = (text or "").strip()
    if not text:
        raise Denied("Write a message first.")
    if len(text) > settings.MESSAGING_MAX_LENGTH:
        raise Denied(f"Messages can be at most {settings.MESSAGING_MAX_LENGTH} characters.")
    return text


def find_user(username):
    user = get_user_model().objects.filter(username__iexact=(username or "").strip(), is_active=True).first()
    if user is None or not user.username:
        raise Denied("No member has that username.")
    return user


def between(one, two):
    a, b = Conversation.pair(one, two)
    return Conversation.objects.filter(user_a=a, user_b=b).first()


def _post(conversation, sender, text):
    message = Message(conversation=conversation, sender=sender)
    message.set_text(text)
    message.save()
    Conversation.objects.filter(pk=conversation.pk).update(last_message_at=message.created_at)
    _mark_read(conversation, sender, message.pk)
    transaction.on_commit(lambda: events.conversation_changed(conversation, message.pk))
    return message


def _screen(sender, text, confirmed):
    """The offensive-message check. It only warns: unconfirmed flagged text raises
    NeedsConfirmation; confirmed text is sent. Only the fact of the warning is recorded."""
    from moderation.detection import may_be_offensive
    from moderation.services import record_flag
    if not may_be_offensive(text):
        return False
    if not confirmed:
        record_flag(sender, "warned")
        raise NeedsConfirmation()
    return True


def start(sender, username, text, confirmed=False):
    """Message someone by username: into the existing conversation, or a new request."""
    text = clean_text(text)
    recipient = find_user(username)
    reason = policy.restriction(sender)
    if reason:
        raise Denied(reason)
    flagged = _screen(sender, text, confirmed)
    with transaction.atomic():
        conversation = between(sender, recipient)
        if conversation is None:
            policy.check_start(sender, recipient)
            policy.check_new_conversation_rate(sender)
            a, b = Conversation.pair(sender, recipient)
            conversation = Conversation.objects.create(user_a=a, user_b=b, initiator=sender)
        elif conversation.state == Conversation.DECLINED and conversation.initiator_id != sender.pk:
            # The person who declined is now writing first: that accepts the conversation.
            policy.check_start(sender, recipient)
            conversation.state, conversation.initiator = Conversation.ACCEPTED, sender
            conversation.save(update_fields=["state", "initiator"])
        return conversation, send(sender, conversation, text, checked_text=True, confirmed=True,
                                  flagged=flagged)


def send(sender, conversation, text, checked_text=False, confirmed=False, flagged=None):
    text = text if checked_text else clean_text(text)
    policy.check_send(sender, conversation)
    if flagged is None:
        flagged = _screen(sender, text, confirmed)
    policy.check_message_rate(sender)
    message = _post(conversation, sender, text)
    if flagged:
        from moderation.services import record_flag
        record_flag(sender, "sent_anyway")
    return message


def accept(user, conversation):
    if not conversation.is_request_for(user):
        raise Denied("There's no request to accept here.")
    conversation.state = Conversation.ACCEPTED
    conversation.save(update_fields=["state"])
    events.conversation_changed(conversation)


def decline(user, conversation):
    if not conversation.is_request_for(user):
        raise Denied("There's no request to decline here.")
    conversation.state = Conversation.DECLINED
    conversation.save(update_fields=["state"])
    events.conversation_changed(conversation)


def _mark_read(conversation, user, upto):
    field = "a_read_upto" if conversation.user_a_id == user.pk else "b_read_upto"
    Conversation.objects.filter(pk=conversation.pk, **{f"{field}__lt": upto}).update(**{field: upto})


def mark_read(user, conversation, upto):
    newest = conversation.messages.order_by("-pk").values_list("pk", flat=True).first() or 0
    _mark_read(conversation, user, min(int(upto), newest))


def block(user, other):
    if other.pk == user.pk:
        raise Denied("You can't block yourself.")
    Block.objects.get_or_create(blocker=user, blocked=other)


def unblock(user, other):
    Block.objects.filter(blocker=user, blocked=other).delete()


def set_preference(user, who):
    if who not in dict(MessagingPreference.CHOICES):
        raise Denied("Choose Everyone or Nobody.")
    MessagingPreference.objects.update_or_create(user=user, defaults={"who_can_message": who})


def preference(user):
    pref = MessagingPreference.objects.filter(user=user).first()
    return pref.who_can_message if pref else MessagingPreference.EVERYONE


# ---------- reading ----------

def when_label(moment):
    """'14:05' for today, '28 Oct' for earlier (site time zone)."""
    local = timezone.localtime(moment)
    return f"{local:%H:%M}" if local.date() == timezone.localdate() else f"{local.day} {local:%b}"


def serialize(message, viewer, reported=frozenset()):
    sender = message.sender
    return {
        "id": message.pk,
        "mine": message.sender_id == viewer.pk,
        "sender": sender.username if sender else None,      # None: "Deleted user"
        "text": message.text,
        "removed": message.removed,
        "can_report": message.sender_id not in (None, viewer.pk) and not message.removed,
        "reported": message.pk in reported,
        "at": timezone.localtime(message.created_at).isoformat(),
    }


def messages_after(conversation, viewer, after=0, before=None):
    """Newest PAGE messages, or only those after `after` (polling), or older than `before`."""
    qs = conversation.messages.select_related("sender")
    if before:
        rows = list(qs.filter(pk__lt=before).order_by("-pk")[:PAGE])[::-1]
    elif after:
        rows = list(qs.filter(pk__gt=after).order_by("pk")[:PAGE])
    else:
        rows = list(qs.order_by("-pk")[:PAGE])[::-1]
    from moderation.models import Report
    reported = set(Report.objects.filter(reporter=viewer, message__in=[m.pk for m in rows])
                   .values_list("message_id", flat=True))
    return [serialize(m, viewer, reported) for m in rows]


def conversation_status(viewer, conversation):
    """What the viewer may do here, in plain words (for the composer)."""
    try:
        policy.check_send(viewer, conversation)
        return {"can_send": True, "reason": ""}
    except Denied as exc:
        return {"can_send": False, "reason": str(exc)}


def inbox(user, tab="inbox", query=""):
    """Rows for the conversation list: the other person, last message preview, unread count."""
    my_upto = Case(When(user_a=user, then=F("a_read_upto")), default=F("b_read_upto"))
    unread = Message.objects.filter(conversation=OuterRef("pk"), pk__gt=OuterRef("my_upto")).exclude(sender=user)\
        .order_by().values("conversation").annotate(n=Count("pk")).values("n")[:1]
    last = Message.objects.filter(conversation=OuterRef("pk")).order_by("-pk").values("pk")[:1]
    qs = (Conversation.objects.involving(user).select_related("user_a", "user_b")
          .annotate(my_upto=my_upto).annotate(unread=Subquery(unread), last_id=Subquery(last)))
    if tab == "requests":
        qs = qs.filter(state=Conversation.PENDING).exclude(initiator=user)
    else:
        qs = qs.filter(Q(state=Conversation.ACCEPTED) | Q(state=Conversation.PENDING, initiator=user)
                       | Q(state=Conversation.DECLINED, initiator=user))
    needle = (query or "").strip()
    if needle:                                   # search by the other person's username only
        qs = qs.filter(Q(user_a=user, user_b__username__icontains=needle)
                       | Q(user_b=user, user_a__username__icontains=needle))
    rows = list(qs.order_by("-last_message_at")[:200])
    last_messages = {m.pk: m for m in Message.objects.filter(pk__in=[c.last_id for c in rows if c.last_id])}
    blocked = set(Block.objects.filter(blocker=user).values_list("blocked_id", flat=True))
    blocked_me = set(Block.objects.filter(blocked=user).values_list("blocker_id", flat=True))
    out = []
    for c in rows:
        other = c.other(user)
        last_message = last_messages.get(c.last_id)
        preview = ""
        if last_message is not None:
            preview = "Message removed" if last_message.removed else last_message.text[:PREVIEW_LENGTH]
        out.append({
            "id": str(c.public_id),
            "username": other.username if other else None,
            # Someone who blocked you: no photo (not even their avatar token).
            "avatar_url": default_avatar_url() if not other or other.pk in blocked_me else avatar_url(other),
            "preview": preview,
            "mine_last": bool(last_message and last_message.sender_id == user.pk),
            "at": timezone.localtime(c.last_message_at).isoformat(),
            "when": when_label(c.last_message_at),
            "unread": c.unread or 0,
            "state": c.state,
            "waiting": c.state == Conversation.PENDING and c.initiator_id == user.pk,
            "blocked": bool(other and other.pk in blocked),
        })
    return out


def request_count(user):
    return Conversation.objects.involving(user).filter(state=Conversation.PENDING).exclude(initiator=user).count()


def export_for(user):
    """The user's messaging data for the personal-data export: every message in their
    conversations (both sides; the other person is named by username only), their setting and
    the members they blocked."""
    rows = []
    conversations = Conversation.objects.involving(user).select_related("user_a", "user_b")
    for conversation in conversations:
        other = conversation.other(user)
        for message in conversation.messages.select_related("sender").order_by("pk"):
            rows.append({
                "conversation": str(conversation.public_id),
                "with": other.username if other else "Deleted user",
                "from": "you" if message.sender_id == user.pk else (
                    message.sender.username if message.sender else "Deleted user"),
                "text": "" if message.removed else message.text,
                "sent_at": message.created_at,
            })
    blocked = Block.objects.filter(blocker=user).select_related("blocked").order_by("created_at")
    return {
        "messages": rows,
        "message_settings": {"who_can_message": preference(user)},
        "blocked_members": [{"username": b.blocked.username, "blocked_at": b.created_at} for b in blocked],
    }


def search_people(user, query, limit=10):
    """Members to start a conversation with. People who blocked you never appear."""
    query = (query or "").strip()
    if len(query) < 2:
        return []
    hidden = Block.objects.filter(blocked=user).values("blocker")
    people = (get_user_model().objects.filter(is_active=True, username__icontains=query)
              .exclude(pk=user.pk).exclude(username="").exclude(pk__in=hidden).order_by("username")[:limit])
    return [{"username": p.username, "avatar_url": avatar_url(p)} for p in people]
