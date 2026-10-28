from django.urls import path

from .consumers import InboxConsumer

websocket_urlpatterns = [
    path("ws/messages/", InboxConsumer.as_asgi()),
]
