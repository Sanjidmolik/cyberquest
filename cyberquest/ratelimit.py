"""
Lightweight request throttling using Django's cache (no extra packages).
"""

from functools import wraps

from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect


def client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    return request.META.get("REMOTE_ADDR") or "unknown"


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
