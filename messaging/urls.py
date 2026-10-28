from django.urls import path

from . import views

app_name = "messaging"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("new/", views.new_message, name="new"),
    path("settings/", views.messaging_settings, name="settings"),
    path("c/<uuid:public_id>/", views.inbox, name="conversation"),
    path("c/<uuid:public_id>/accept/", views.respond, {"action": "accept"}, name="accept"),
    path("c/<uuid:public_id>/decline/", views.respond, {"action": "decline"}, name="decline"),
    path("block/", views.block_toggle, {"action": "block"}, name="block"),
    path("unblock/", views.block_toggle, {"action": "unblock"}, name="unblock"),
    path("api/inbox/", views.api_inbox, name="api_inbox"),
    path("api/c/<uuid:public_id>/send/", views.api_send, name="api_send"),
    path("api/c/<uuid:public_id>/poll/", views.api_poll, name="api_poll"),
    path("api/c/<uuid:public_id>/read/", views.api_read, name="api_read"),
]
