from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from .models import Notification


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
    """Click a notification -> send them to its link, if it has one."""
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    return redirect(notification.link_url or "dashboard:home")
