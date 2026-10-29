"""Who may message whom. Every send path (views, API, and anything later) goes through here.

- One-to-one only. A first message from someone new is a request until the recipient accepts.
- "Who can message me: Nobody" stops new requests; people already accepted can still reply.
- A block (either way) stops all messages between the two.
- Rate limits: messages per minute and new conversations per day, per user (settings).
- Moderation (feature 3) adds mutes and suspensions through `restriction()`.
"""

from django.conf import settings
from django.db.models import Q

from cyberquest.ratelimit import is_rate_limited

from .models import Block, Conversation, MessagingPreference


class Denied(Exception):
    """A plain-English reason the action isn't allowed."""


class RateLimited(Denied):
    """Too many messages or new conversations; try again later."""


class NeedsConfirmation(Denied):
    """The text may be offensive: the sender must edit it or confirm sending it anyway."""

    def __init__(self):
        super().__init__("This message may be offensive. Edit it, or send it anyway.")


def blocked_between(one, two):
    """True if either person has blocked the other."""
    return Block.objects.filter(Q(blocker=one, blocked=two) | Q(blocker=two, blocked=one)).exists()


def accepts_new_messages(user):
    pref = MessagingPreference.objects.filter(user=user).first()
    return pref is None or pref.who_can_message == MessagingPreference.EVERYONE


def can_be_messaged(user):
    return bool(user is not None and user.is_active and user.username)


def restriction(user):
    """Why this user can't send messages right now (a moderator's mute or suspension), or ""."""
    from moderation.services import restriction_reason
    return restriction_reason(user)


def check_start(sender, recipient):
    if recipient.pk == sender.pk:
        raise Denied("You can't message yourself.")
    if not can_be_messaged(recipient):
        raise Denied("This person can't receive messages.")
    if blocked_between(sender, recipient):
        raise Denied("You can't message this person.")
    if not accepts_new_messages(recipient):
        raise Denied(f"{recipient.username} isn't accepting new messages.")


def check_send(sender, conversation):
    reason = restriction(sender)
    if reason:
        raise Denied(reason)
    other = conversation.other(sender)
    if not can_be_messaged(other):
        raise Denied("This person can't receive messages any more.")
    if blocked_between(sender, other):
        raise Denied("You can't message this person.")
    if conversation.state == Conversation.DECLINED:
        raise Denied("This message request wasn't accepted.")
    if conversation.state == Conversation.PENDING and conversation.initiator_id != sender.pk:
        raise Denied("Accept this request to reply.")


def check_message_rate(sender):
    if is_rate_limited(f"msg:minute:{sender.pk}", limit=settings.MESSAGING_MESSAGES_PER_MINUTE, window_seconds=60):
        raise RateLimited("You're sending messages too quickly. Wait a minute and try again.")


def check_timer_rate(user):
    if is_rate_limited(f"msg:timer:{user.pk}", limit=settings.MESSAGING_TIMER_CHANGES_PER_HOUR, window_seconds=3600):
        raise RateLimited("You've changed disappearing messages too often. Try again in an hour.")


def check_new_conversation_rate(sender):
    if is_rate_limited(f"msg:newconv:{sender.pk}", limit=settings.MESSAGING_NEW_CONVERSATIONS_PER_DAY,
                       window_seconds=86_400):
        raise RateLimited("You've started the maximum number of new conversations for today. Try again tomorrow.")
