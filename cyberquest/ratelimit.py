"""
Lightweight request throttling using Django's cache (no extra packages).

The cache backend is the database, so counters are shared by every worker
and survive a process restart. Client IPs come from REMOTE_ADDR unless this
process is behind Render, in which case the rightmost X-Forwarded-For entry
is the address Render itself appended.
"""

import ipaddress
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect


def _valid_ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return ""


def client_ip(request) -> str:
    """Return the client address the hosting proxy actually observed."""
    remote = _valid_ip(request.META.get("REMOTE_ADDR") or "") or "unknown"
    if not getattr(settings, "BEHIND_RENDER_PROXY", False):
        return remote
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR") or ""
    parts = [part.strip() for part in forwarded.split(",") if part.strip()]
    if not parts:
        return remote
    # Render appends the connecting client. Earlier values are caller-supplied.
    return _valid_ip(parts[-1]) or remote


def is_rate_limited(key: str, *, limit: int, window_seconds: int) -> bool:
    """Return True when the keyed counter has already reached ``limit``."""
    count = cache.get(key)
    if count is None:
        cache.set(key, 1, window_seconds)
        return False
    if int(count) >= limit:
        return True
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, window_seconds)
    return False


def rate_limit(
    *,
    key_prefix: str,
    limit: int,
    window_seconds: int,
    methods=("POST",),
    message: str = "Too many attempts. Please wait a few minutes and try again.",
):
    """Decorator: block repeated POSTs from the same client IP."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method in methods:
                ip = client_ip(request)
                key = f"rl:{key_prefix}:{ip}"
                if is_rate_limited(key, limit=limit, window_seconds=window_seconds):
                    accepts = request.headers.get("Accept", "")
                    wants_json = (
                        "application/json" in (request.content_type or "")
                        or "application/json" in accepts
                    )
                    if wants_json:
                        return JsonResponse({"error": message}, status=429)
                    messages.error(request, message)
                    if request.method == "POST":
                        return redirect(request.path)
                    return HttpResponse(message, status=429)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
