"""The moderation panel in the Admin Command Center (Moderator group or superusers only).

Reported content is never on the report page itself: a moderator presses "Show reported
message" (a POST), which writes a "viewed" entry to the moderation log and returns the
content in that response only. Reports a moderator filed, or that are about them, are
hidden from them and return 404.
"""

import base64

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from messaging.policy import Denied

from . import services
from .access import moderator_required
from .models import ModerationLog, Report, Restriction


def _shell(request, title, **extra):
    extra.update({"active": "moderation", "page_title": title})
    if request.user.is_superuser:
        from pages.models import ContactMessage
        extra["open_contact"] = ContactMessage.objects.filter(is_resolved=False).count()
    return extra


def _report(request, pk):
    """Any report, except ones this moderator filed or that are about them (404 for those)."""
    report = (Report.objects.select_related("reporter", "reported_user").filter(pk=pk)
              .exclude(reporter=request.user).exclude(reported_user=request.user).first())
    if report is None:
        raise Http404("Report not found.")
    return report


FORM_LABELS = {
    "dismiss": "Dismiss: no action needed", "warn": "Warn the member",
    "mute_24h": "Mute messaging for 24 hours", "mute_7d": "Mute messaging for 7 days",
    "suspend": "Suspend messaging until lifted",
}


def _choices():
    return [(key, FORM_LABELS[key]) for key in services.ACTIONS]


@moderator_required
def queue(request):
    status = Report.RESOLVED if request.GET.get("status") == "resolved" else Report.OPEN
    rows = services.queue_for(request.user, status).order_by("created_at" if status == Report.OPEN else "-resolved_at")
    page = Paginator(rows, 25).get_page(request.GET.get("page") or 1)
    return render(request, "moderation/panel/queue.html", _shell(
        request, "Reports", page=page, status=status, flags=services.flag_counts(),
        open_count=services.queue_for(request.user).count(),
    ))


@moderator_required
def report_detail(request, pk):
    report = _report(request, pk)
    context = {"report": report, "action_choices": _choices(), "rows": None, "note": None,
               "history": ModerationLog.objects.filter(report=report).select_related("actor")}
    return render(request, "moderation/panel/report.html", _shell(request, f"Report {report.pk}", **context))


@moderator_required
@require_POST
def reveal(request, pk):
    report = _report(request, pk)
    rows, note = services.reveal(request.user, report)
    photo = services.reported_photo(report)
    context = {"report": report, "action_choices": _choices(), "rows": rows, "note": note,
               # Inline in this logged, no-store response only: the photo never gets a URL.
               "photo": ({"type": photo[1], "data": base64.b64encode(photo[0]).decode("ascii")} if photo else None),
               "history": ModerationLog.objects.filter(report=report).select_related("actor")}
    response = render(request, "moderation/panel/report.html", _shell(request, f"Report {report.pk}", **context))
    response["Cache-Control"] = "no-store"
    return response


@moderator_required
@require_POST
def act(request, pk):
    report = _report(request, pk)
    try:
        services.act(request.user, report, request.POST.get("action"), request.POST.get("reason"))
    except Denied as exc:
        messages.error(request, str(exc))
        return redirect("moderation:report", pk=report.pk)
    messages.success(request, "Done. The action is in the moderation log.")
    return redirect("moderation:queue")


@moderator_required
def restrictions(request):
    rows = Restriction.objects.active().select_related("user", "created_by").exclude(user=request.user)
    return render(request, "moderation/panel/restrictions.html", _shell(request, "Active restrictions", rows=rows))


@moderator_required
@require_POST
def lift(request, pk):
    restriction = get_object_or_404(Restriction.objects.exclude(user=request.user), pk=pk)
    try:
        services.lift(request.user, restriction, request.POST.get("reason"))
    except Denied as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Restriction lifted.")
    return redirect("moderation:restrictions")


@moderator_required
def log(request):
    rows = ModerationLog.objects.select_related("actor", "subject")
    page = Paginator(rows, 50).get_page(request.GET.get("page") or 1)
    return render(request, "moderation/panel/log.html", _shell(request, "Moderation log", page=page))
