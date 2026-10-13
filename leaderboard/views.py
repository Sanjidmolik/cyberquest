"""
leaderboard/views.py
------------------------
Shows the top users ranked by total XP. Uses the `username` field that
was specifically collected at signup for exactly this purpose.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib.auth import get_user_model

UserModel = get_user_model()


@login_required(login_url="/accounts/login/")
def leaderboard_view(request):
    top_users = (
        UserModel.objects.filter(is_active=True)
        .exclude(username__isnull=True)
        .exclude(username="")
        .order_by("-xp")[:20]
    )

    # Rank = number of active named users with strictly more XP, plus one.
    # Ties are counted as the same rank (users with equal XP share a position).
    base_qs = UserModel.objects.filter(is_active=True).exclude(username__isnull=True).exclude(username="")
    my_rank = None
    if request.user.username:
        users_ahead = base_qs.filter(xp__gt=request.user.xp).count()
        my_rank = users_ahead + 1

    return render(request, "leaderboard/leaderboard.html", {
        "top_users": top_users,
        "my_rank": my_rank,
    })
