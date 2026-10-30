"""Messaging actions. Views and the API call these; each one checks the rules in policy.py."""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.models import Case, Count, F, OuterRef, Q, Subquery, When
from django.utils import timezone

from accounts.public import avatar_url, default_avatar_url

from . import events, policy
from .models import AFTER_VIEW, OFF, TIMERS, VIEW_GRACE, Block, Conversation, Message, MessagingPreference, expiry_for
from .policy import Denied, NeedsConfirmation

PREVIEW_LENGTH = 80
PAGE = 50
ONLINE_WINDOW = timedelta(minutes=2)   # "online" = a heartbeat this recent
HEARTBEAT_SECONDS = 60                 # write last_seen_at at most this often per user


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


def _post(conversation, sender, text, kind=Message.TEXT):
    """Store a message. It takes the conversation's CURRENT timer (read fresh, so a change
    made a moment ago applies); system notices never disappear."""
    timer = OFF if kind == Message.SYSTEM else (
        Conversation.objects.filter(pk=conversation.pk).values_list("disappear_after", flat=True).first() or OFF)
    now = timezone.now()
    message = Message(conversation=conversation, sender=sender, kind=kind, timer=timer, created_at=now,
                      expires_at=expiry_for(timer, now))
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
            timer = default_timer(sender)
            conversation = Conversation.objects.create(user_a=a, user_b=b, initiator=sender, disappear_after=timer)
            if timer != OFF:
                _post(conversation, sender, timer_notice(sender, timer), kind=Message.SYSTEM)
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


def timer_notice(user, timer):
    if timer == OFF:
        return f"{user.username} turned off disappearing messages"
    return f"{user.username} set disappearing messages to {TIMERS[timer][0].lower()}"


def set_timer(user, conversation, timer):
    """Either participant who may send here can change the timer. It applies to messages sent
    after the change, and leaves a notice in the chat. Returns the notice (or None if unchanged)."""
    if timer not in TIMERS:
        raise Denied("Choose a disappearing-messages setting.")
    policy.check_send(user, conversation)
    policy.check_timer_rate(user)
    with transaction.atomic():
        changed = Conversation.objects.filter(pk=conversation.pk).exclude(disappear_after=timer)            .update(disappear_after=timer)
        if not changed:
            return None
        conversation.disappear_after = timer
        return _post(conversation, user, timer_notice(user, timer), kind=Message.SYSTEM)


def default_timer(user):
    pref = MessagingPreference.objects.filter(user=user).first()
    return pref.default_timer if pref else OFF


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
    # "After viewing": the other person's messages start their 30-second countdown once read.
    Message.objects.filter(conversation=conversation, pk__lte=upto, timer=AFTER_VIEW, kind=Message.TEXT,
                           expires_at__isnull=True).exclude(sender=user)        .update(expires_at=timezone.now() + VIEW_GRACE)


def _newest(conversation):
    return conversation.messages.order_by("-pk").values_list("pk", flat=True).first() or 0


def mark_read(user, conversation, upto):
    upto = min(int(upto), _newest(conversation))
    field = "a_read_upto" if conversation.user_a_id == user.pk else "b_read_upto"
    advanced = Conversation.objects.filter(pk=conversation.pk, **{f"{field}__lt": upto}).exists()
    _mark_read(conversation, user, upto)
    if advanced:                                   # the sender's ticks can turn "read"
        transaction.on_commit(lambda: events.conversation_changed(conversation))


def mark_delivered(user, conversation, upto=None):
    """The user's client has fetched messages up to `upto` (default: the newest visible)."""
    upto = _newest(conversation) if upto is None else min(int(upto), _newest(conversation))
    field = "a_delivered_upto" if conversation.user_a_id == user.pk else "b_delivered_upto"
    if Conversation.objects.filter(pk=conversation.pk, **{f"{field}__lt": upto}).update(**{field: upto}):
        transaction.on_commit(lambda: events.conversation_changed(conversation))


# ---------- receipts and presence (reciprocal; nothing at all across a block) ----------

def _prefs(*users):
    found = {p.user_id: p for p in MessagingPreference.objects.filter(user__in=[u for u in users if u])}
    return [found.get(u.pk) if u else None for u in users]


def _wants(pref, field):
    return True if pref is None else getattr(pref, field)


def receipts(viewer, conversation):
    """How far the other person got with the viewer's messages: {"delivered_upto", "read_upto"}.
    Read receipts show only when BOTH people have them on; a block hides both (just "sent")."""
    other = conversation.other(viewer)
    if other is None or policy.blocked_between(viewer, other):
        return {"delivered_upto": 0, "read_upto": 0}
    fresh = Conversation.objects.filter(pk=conversation.pk).values(
        "a_read_upto", "b_read_upto", "a_delivered_upto", "b_delivered_upto").first()
    side = "b" if conversation.user_a_id == viewer.pk else "a"
    read, delivered = fresh[f"{side}_read_upto"], fresh[f"{side}_delivered_upto"]
    mine, theirs = _prefs(viewer, other)
    show_read = _wants(mine, "read_receipts") and _wants(theirs, "read_receipts")
    return {"delivered_upto": max(read, delivered), "read_upto": read if show_read else 0}


def message_status(message_id, seen):
    if message_id <= seen["read_upto"]:
        return "read"
    return "delivered" if message_id <= seen["delivered_upto"] else "sent"


def touch_presence(user):
    """The presence heartbeat, written at most once a minute per user."""
    if not cache.add(f"msg:seen:{user.pk}", 1, HEARTBEAT_SECONDS):
        return
    now = timezone.now()
    if not MessagingPreference.objects.filter(user=user).update(last_seen_at=now):
        MessagingPreference.objects.get_or_create(user=user, defaults={"last_seen_at": now})


def _is_online(viewer_pref, other_pref, now):
    if not (_wants(viewer_pref, "show_online") and _wants(other_pref, "show_online")):
        return False                               # reciprocal, like read receipts
    seen = other_pref.last_seen_at if other_pref else None
    return bool(seen and now - seen <= ONLINE_WINDOW)


def is_online(viewer, conversation):
    """Only accepted contacts see each other online, never across a block."""
    other = conversation.other(viewer)
    if other is None or conversation.state != Conversation.ACCEPTED or policy.blocked_between(viewer, other):
        return False
    return _is_online(*_prefs(viewer, other), timezone.now())


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


def set_privacy(user, *, read_receipts, show_online, default_timer):
    if default_timer not in TIMERS:
        raise Denied("Choose a default for disappearing messages.")
    MessagingPreference.objects.update_or_create(user=user, defaults={
        "read_receipts": bool(read_receipts), "show_online": bool(show_online), "default_timer": default_timer})


def privacy(user):
    pref = MessagingPreference.objects.filter(user=user).first()
    return {"read_receipts": _wants(pref, "read_receipts"), "show_online": _wants(pref, "show_online"),
            "default_timer": pref.default_timer if pref else OFF}


def preference(user):
    pref = MessagingPreference.objects.filter(user=user).first()
    return pref.who_can_message if pref else MessagingPreference.EVERYONE


# ---------- reading ----------

def when_label(moment):
    """'14:05' for today, '28 Oct' for earlier (site time zone)."""
    local = timezone.localtime(moment)
    return f"{local:%H:%M}" if local.date() == timezone.localdate() else f"{local.day} {local:%b}"


def serialize(message, viewer, reported=frozenset(), seen=None):
    sender = message.sender
    ticks = message.sender_id == viewer.pk and message.kind != Message.SYSTEM
    return {
        # Ticks on your own messages only: "sent", "delivered" or "read" (see receipts()).
        "status": (message_status(message.pk, seen) if seen else "sent") if ticks else None,
        "id": message.pk,
        "kind": message.kind,
        "timer": message.timer,
        "expires_at": timezone.localtime(message.expires_at).isoformat() if message.expires_at else None,
        "mine": message.sender_id == viewer.pk,
        "sender": sender.username if sender else None,      # None: "Deleted user"
        "text": message.text,
        # View-once photos: never a URL here; the recipient opens it once through api_photo_open.
        "photo": ({"state": "opened" if message.photo_opened_at else "view_once",
                   "can_open": (message.sender_id != viewer.pk and not message.photo_opened_at
                                and bool(message.photo))}
                  if message.kind == Message.PHOTO else None),
        "removed": message.removed,
        "can_report": (message.sender_id not in (None, viewer.pk) and not message.removed
                       and message.kind != Message.SYSTEM),
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
    seen = receipts(viewer, conversation)
    return [serialize(m, viewer, reported, seen) for m in rows]


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
    my_delivered = Case(When(user_a=user, then=F("a_delivered_upto")), default=F("b_delivered_upto"))
    unread = Message.objects.filter(conversation=OuterRef("pk"), pk__gt=OuterRef("my_upto")).exclude(sender=user)\
        .order_by().values("conversation").annotate(n=Count("pk")).values("n")[:1]
    last = Message.objects.filter(conversation=OuterRef("pk")).order_by("-pk").values("pk")[:1]
    qs = (Conversation.objects.involving(user).select_related("user_a", "user_b")
          .annotate(my_upto=my_upto, my_delivered=my_delivered)
          .annotate(unread=Subquery(unread), last_id=Subquery(last)))
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
    others = [c.other(user) for c in rows]
    prefs = {p.user_id: p for p in MessagingPreference.objects.filter(user__in=[o for o in others if o] + [user])}
    now = timezone.now()
    out = []
    for c, other in zip(rows, others):
        last_message = last_messages.get(c.last_id)
        preview = ""
        if last_message is not None:
            if last_message.removed:
                preview = "Message removed"
            elif last_message.kind == Message.PHOTO:
                from .photos import preview as photo_preview
                preview = photo_preview(last_message, user)
            else:
                preview = last_message.text[:PREVIEW_LENGTH]
            if last_message.sender_id != user.pk and c.last_id > (c.my_delivered or 0):
                mark_delivered(user, c, c.last_id)       # the inbox list fetched it: delivered
        cut_off = other is None or other.pk in blocked or other.pk in blocked_me
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
            "timer": c.disappear_after,
            "timer_label": "" if c.disappear_after == OFF else TIMERS[c.disappear_after][0].lower(),
            "online": bool(not cut_off and c.state == Conversation.ACCEPTED
                           and _is_online(prefs.get(user.pk), prefs.get(other.pk), now)),
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
            if message.kind == Message.PHOTO:     # never the picture itself: it is view-once
                text = "[view-once photo, opened]" if message.photo_opened_at else "[view-once photo, not opened]"
            else:
                text = "" if message.removed else message.text
            rows.append({
                "conversation": str(conversation.public_id),
                "with": other.username if other else "Deleted user",
                "from": "you" if message.sender_id == user.pk else (
                    message.sender.username if message.sender else "Deleted user"),
                "kind": message.kind,
                "text": text,
                "sent_at": message.created_at,
                "disappearing": TIMERS.get(message.timer, ("Off", None))[0],
                "expires_at": message.expires_at,
            })
    blocked = Block.objects.filter(blocker=user).select_related("blocked").order_by("created_at")
    return {
        "messages": rows,
        "message_settings": {"who_can_message": preference(user), **privacy(user),
                             "last_active_in_messages": getattr(
                                 MessagingPreference.objects.filter(user=user).first(), "last_seen_at", None)},
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
