"""Inbox pages and the small JSON API the inbox script uses (send, poll, read).

Every conversation is looked up among the signed-in user's own conversations, so anyone
else gets 404 for every URL. Message text is returned as JSON and inserted with textContent;
templates rely on autoescaping.
"""

import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from accounts.public import public_card

from . import services
from .models import Block, Conversation, MessagingPreference
from .policy import Denied, RateLimited

LOGIN_URL = "/accounts/login/"


def _conversation(request, public_id):
    conversation = (Conversation.objects.involving(request.user).select_related("user_a", "user_b")
                    .filter(public_id=public_id).first())
    if conversation is None:
        raise Http404("Conversation not found.")
    return conversation


def _body(request):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _back(request, fallback):
    target = request.POST.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                  require_https=request.is_secure()):
        return redirect(target)
    return redirect(fallback)


def _int(raw):
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


@login_required(login_url=LOGIN_URL)
@require_GET
def inbox(request, public_id=None):
    tab = "requests" if request.GET.get("tab") == "requests" else "inbox"
    conversation = _conversation(request, public_id) if public_id else None
    if conversation is not None and conversation.is_request_for(request.user):
        tab = "requests"
    context = {
        "tab": tab,
        "query": request.GET.get("q", "")[:50],
        "rows": services.inbox(request.user, tab, request.GET.get("q", "")[:50]),
        "requests": services.request_count(request.user),
        "conversation": None,
    }
    if conversation is not None:
        other = conversation.other(request.user)
        status = services.conversation_status(request.user, conversation)
        context.update({
            "conversation": conversation,
            "other": other,
            "card": public_card(other, request.user) if other else None,
            "is_request": conversation.is_request_for(request.user),
            "i_blocked": bool(other and Block.objects.filter(blocker=request.user, blocked=other).exists()),
            "status": status,
            "config": {
                "conversation": str(conversation.public_id),
                "messages": services.messages_after(conversation, request.user),
                "status": status,
                "max": settings.MESSAGING_MAX_LENGTH,
                "urls": {
                    "send": reverse("messaging:api_send", args=[conversation.public_id]),
                    "poll": reverse("messaging:api_poll", args=[conversation.public_id]),
                    "read": reverse("messaging:api_read", args=[conversation.public_id]),
                    "inbox": reverse("messaging:api_inbox"),
                },
            },
        })
    else:
        context["config"] = {"conversation": None, "urls": {"inbox": reverse("messaging:api_inbox")}, "tab": tab}
    context["config"]["tab"] = tab
    context["config"]["socket"] = "/ws/messages/"
    return render(request, "messaging/inbox.html", context)


@login_required(login_url=LOGIN_URL)
def new_message(request):
    if request.method == "POST":
        username = request.POST.get("username", "")
        try:
            conversation, _ = services.start(request.user, username, request.POST.get("text", ""))
        except Denied as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('messaging:new')}?to={username[:50]}")
        return redirect("messaging:conversation", public_id=conversation.public_id)
    query = request.GET.get("q", "")[:50]
    to = request.GET.get("to", "")[:50]
    return render(request, "messaging/new.html", {
        "query": query, "to": to,
        "people": services.search_people(request.user, query),
        "max": settings.MESSAGING_MAX_LENGTH,
    })


@login_required(login_url=LOGIN_URL)
@require_POST
def api_send(request, public_id):
    conversation = _conversation(request, public_id)
    try:
        message = services.send(request.user, conversation, _body(request).get("text"))
    except RateLimited as exc:
        return JsonResponse({"error": str(exc)}, status=429)
    except Denied as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"message": services.serialize(message, request.user)}, status=201)


@login_required(login_url=LOGIN_URL)
@require_GET
def api_poll(request, public_id):
    """Only messages newer than ?after=<id> (or older than ?before=<id>): cheap to call often."""
    conversation = _conversation(request, public_id)
    rows = services.messages_after(conversation, request.user, after=_int(request.GET.get("after")),
                                   before=_int(request.GET.get("before")) or None)
    return JsonResponse({"messages": rows, "state": conversation.state,
                         "status": services.conversation_status(request.user, conversation)})


@login_required(login_url=LOGIN_URL)
@require_POST
def api_read(request, public_id):
    conversation = _conversation(request, public_id)
    services.mark_read(request.user, conversation, _int(_body(request).get("upto")))
    return JsonResponse({"ok": True})


@login_required(login_url=LOGIN_URL)
@require_GET
def api_inbox(request):
    tab = "requests" if request.GET.get("tab") == "requests" else "inbox"
    return JsonResponse({"rows": services.inbox(request.user, tab, request.GET.get("q", "")[:50]),
                         "requests": services.request_count(request.user)})


@login_required(login_url=LOGIN_URL)
@require_POST
def respond(request, public_id, action):
    conversation = _conversation(request, public_id)
    try:
        (services.accept if action == "accept" else services.decline)(request.user, conversation)
    except Denied as exc:
        messages.error(request, str(exc))
    if action == "accept":
        return redirect("messaging:conversation", public_id=conversation.public_id)
    messages.success(request, "Request declined.")
    return redirect(f"{reverse('messaging:inbox')}?tab=requests")


@login_required(login_url=LOGIN_URL)
@require_POST
def block_toggle(request, action):
    try:
        other = services.find_user(request.POST.get("username"))
        (services.block if action == "block" else services.unblock)(request.user, other)
    except Denied as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"{other.username} is {'blocked' if action == 'block' else 'unblocked'}.")
    return _back(request, reverse("messaging:settings"))


@login_required(login_url=LOGIN_URL)
def messaging_settings(request):
    if request.method == "POST":
        try:
            services.set_preference(request.user, request.POST.get("who_can_message"))
        except Denied as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Saved.")
        return redirect("messaging:settings")
    blocked = Block.objects.filter(blocker=request.user).select_related("blocked").order_by("blocked__username")
    return render(request, "messaging/settings.html", {
        "who": services.preference(request.user),
        "choices": MessagingPreference.CHOICES,
        "blocked": [b.blocked.username for b in blocked if b.blocked.username],
    })
