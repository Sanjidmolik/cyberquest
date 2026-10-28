"""
ASGI config for cyberquest project: HTTP plus the messaging WebSocket.

Used by `manage.py runserver` (daphne) locally and by an ASGI server in production. Gunicorn
keeps using wsgi.py; messaging then works by polling alone.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cyberquest.settings')

# Set up Django before importing anything that touches models.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from messaging.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    # Origin must match ALLOWED_HOSTS (stops other sites opening a socket with the user's
    # cookies); the session identifies the user.
    "websocket": AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns))),
})
