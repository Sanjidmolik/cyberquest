"""WebSocket push for the inbox. It never carries message text: it only says "conversation X
changed", and the browser fetches through the same HTTP API (and its checks) as polling.

- Connect: signed-in, active users only (session auth); others are closed with 4401.
- Every pushed event and every frame from the browser is checked against the user's
  conversations; anything else is dropped.
- Typing indicators exist only here (no polling version): "typing" frames are forwarded to
  the other person of an ACCEPTED conversation, never across a block, at most once every
  TYPING_EVERY seconds per conversation. Checked again when delivered.
"""

import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import ValidationError

from .events import user_group
from .models import Conversation
from .policy import blocked_between

UNAUTHORISED = 4401
TYPING_EVERY = 3


class InboxConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated or not user.is_active:
            await self.close(code=UNAUTHORISED)
            return
        self.user = user
        self.group = user_group(user.pk)
        self.typing_sent = {}
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if getattr(self, "group", None):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    @database_sync_to_async
    def _is_member(self, public_id):
        try:
            return Conversation.objects.involving(self.user).filter(public_id=public_id).exists() \
                and type(self.user).objects.filter(pk=self.user.pk, is_active=True).exists()
        except (ValueError, TypeError, ValidationError):      # not a UUID
            return False

    @database_sync_to_async
    def _typing_target(self, public_id):
        """The other person's id if a typing signal may go to them, else None."""
        try:
            conversation = (Conversation.objects.involving(self.user).select_related("user_a", "user_b")
                            .filter(public_id=public_id, state=Conversation.ACCEPTED).first())
        except (ValueError, TypeError, ValidationError):
            return None
        other = conversation.other(self.user) if conversation else None
        if other is None or not other.is_active or blocked_between(self.user, other):
            return None
        return other.pk

    @database_sync_to_async
    def _may_see_typing(self, public_id, sender_id):
        try:
            conversation = (Conversation.objects.involving(self.user).select_related("user_a", "user_b")
                            .filter(public_id=public_id, state=Conversation.ACCEPTED).first())
        except (ValueError, TypeError, ValidationError):
            return False
        other = conversation.other(self.user) if conversation else None
        return bool(other and other.pk == sender_id and not blocked_between(self.user, other))

    async def receive_json(self, content, **kwargs):
        """Browsers may only ping, ask whether they may watch a conversation, or say they're typing."""
        kind = content.get("type") if isinstance(content, dict) else None
        if kind == "ping":
            await self.send_json({"type": "pong"})
        elif kind == "watch":
            allowed = await self._is_member(str(content.get("conversation") or ""))
            await self.send_json({"type": "watch", "ok": allowed})
        elif kind == "typing":
            public_id = str(content.get("conversation") or "")[:64]
            now = time.monotonic()
            if now - self.typing_sent.get(public_id, -TYPING_EVERY) < TYPING_EVERY:
                return                                     # throttled: dropped quietly
            target = await self._typing_target(public_id)
            if target is None:
                return
            self.typing_sent[public_id] = now
            await self.channel_layer.group_send(user_group(target), {
                "type": "conversation.typing", "conversation": public_id, "sender": self.user.pk})
        else:
            await self.send_json({"type": "error", "error": "Unknown request."})

    async def conversation_typing(self, event):
        if await self._may_see_typing(event.get("conversation", ""), event.get("sender")):
            await self.send_json({"type": "typing", "conversation": event["conversation"]})

    async def conversation_changed(self, event):
        if await self._is_member(event.get("conversation", "")):
            await self.send_json({"type": "changed", "conversation": event["conversation"], "id": event.get("id", 0)})
