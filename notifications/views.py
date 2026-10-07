from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Notification


def _safe_notification_target(request, link_url: str) -> str | None:
    """
    Allow same-origin / relative app paths only. Reject external open redirects.
    Existing rows with unsafe URLs are left in the DB but fall back to dashboard.
    """
    target = (link_url or "").strip()
    if not target:
        return None
    if url_has_allowed_host_and_scheme(
        url=target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return None


@login_required(login_url="/accounts/login/")
def notification_list(request):
    notifications = Notification.objects.filter(user=request.user)
    unread_count = notifications.filter(is_read=False).count()

    # Mark everything as read the moment the user actually views this page
    notifications.filter(is_read=False).update(is_read=True)

    return render(request, "notifications/list.html", {
        "notifications": notifications,
        "unread_count_before_view": unread_count,
    })


@login_required(login_url="/accounts/login/")
def notification_redirect(request, pk):
    """Click a notification -> send them to its link, if it has a safe one."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    target = _safe_notification_target(request, notification.link_url)
    if target:
        return redirect(target)
    return redirect("dashboard:home")
