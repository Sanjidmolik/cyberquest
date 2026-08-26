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

    # Find the current user's own rank too, even if they're outside the top 20
    all_ranked = list(
        UserModel.objects.filter(is_active=True).exclude(username__isnull=True).exclude(username="")
        .order_by("-xp").values_list("id", flat=True)
    )
    my_rank = (all_ranked.index(request.user.id) + 1) if request.user.id in all_ranked else None

    return render(request, "leaderboard/leaderboard.html", {
        "top_users": top_users,
        "my_rank": my_rank,
    })
