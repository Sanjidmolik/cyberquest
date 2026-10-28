"""Tell open WebSockets that something changed. Best effort: the browser also polls, so a
missing or failing channel layer (e.g. Gunicorn/WSGI, or several processes without Redis)
only delays an update until the next poll."""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger("messaging.events")


def user_group(user_id):
    return f"messaging.user.{user_id}"


def conversation_changed(conversation, message_id=None):
    layer = get_channel_layer()
    if layer is None:
        return
    event = {"type": "conversation.changed", "conversation": str(conversation.public_id), "id": message_id or 0}
    for user_id in (conversation.user_a_id, conversation.user_b_id):
        if user_id is None:
            continue
        try:
            async_to_sync(layer.group_send)(user_group(user_id), event)
        except Exception:  # noqa: BLE001 - a push failure must never stop a message being saved
            logger.warning("messaging push failed", exc_info=True)
