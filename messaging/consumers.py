"""WebSocket push for the inbox. It never carries message text: it only says "conversation X
changed", and the browser fetches through the same HTTP API (and its checks) as polling.

- Connect: signed-in, active users only (session auth); others are closed with 4401.
- Every pushed event and every frame from the browser is checked against the user's
  conversations; anything else is dropped.
"""

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import ValidationError

from .events import user_group
from .models import Conversation

UNAUTHORISED = 4401


class InboxConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated or not user.is_active:
            await self.close(code=UNAUTHORISED)
            return
        self.user = user
        self.group = user_group(user.pk)
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

    async def receive_json(self, content, **kwargs):
        """Browsers may only ping, or ask whether they may watch a conversation."""
        kind = content.get("type") if isinstance(content, dict) else None
        if kind == "ping":
            await self.send_json({"type": "pong"})
        elif kind == "watch":
            allowed = await self._is_member(str(content.get("conversation") or ""))
            await self.send_json({"type": "watch", "ok": allowed})
        else:
            await self.send_json({"type": "error", "error": "Unknown request."})

    async def conversation_changed(self, event):
        if await self._is_member(event.get("conversation", "")):
            await self.send_json({"type": "changed", "conversation": event["conversation"], "id": event.get("id", 0)})
