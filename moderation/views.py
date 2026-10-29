"""Member-facing moderation: report a received message, and see your own notices."""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from messaging.policy import Denied, RateLimited

from . import services

LOGIN_URL = "/accounts/login/"


@login_required(login_url=LOGIN_URL)
@require_POST
def report(request):
    try:
        body = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        body = {}
    if not isinstance(body, dict):
        body = {}
    message_id = body.get("message")
    if isinstance(message_id, bool) or not isinstance(message_id, int):
        return JsonResponse({"error": "Message not found."}, status=404)
    try:
        _, created = services.report(request.user, message_id, body.get("reason"), body.get("note"),
                                     also_block=body.get("block") is True)
    except RateLimited as exc:
        return JsonResponse({"error": str(exc)}, status=429)
    except Denied as exc:
        status = 404 if "not found" in str(exc) else 400
        return JsonResponse({"error": str(exc)}, status=status)
    return JsonResponse({"ok": True, "already_reported": not created}, status=201 if created else 200)


@login_required(login_url=LOGIN_URL)
def notices(request):
    return render(request, "moderation/notices.html", {
        "notices": services.notices(request.user),
        "restriction": services.restriction_reason(request.user),
    })
