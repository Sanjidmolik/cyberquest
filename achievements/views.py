"""
achievements/views.py
-------------------------
Shows a user's badge collection: earned badges (with the date), and
locked ones they haven't unlocked yet -- like a game's trophy case.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Badge, UserBadge


@login_required(login_url="/accounts/login/")
def badge_list(request):
    earned = UserBadge.objects.filter(user=request.user).select_related("badge")
    earned_badge_ids = set(earned.values_list("badge_id", flat=True))

    locked = Badge.objects.filter(is_active=True).exclude(id__in=earned_badge_ids)

    return render(request, "achievements/badge_list.html", {
        "earned": earned,
        "locked": locked,
    })
