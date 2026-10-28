"""
leaderboard/views.py
------------------------
The full leaderboard: a top-3 podium, a ranked list in pages, All-time / This month /
This week tabs, and the signed-in user's own rank always in view. Only public fields are
shown (avatar, username, completed courses, XP). Ranking rules live in ranking.py.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from . import ranking


def _page_number(raw):
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


@login_required(login_url="/accounts/login/")
def leaderboard_view(request):
    period = request.GET.get("period", "all")
    if period not in ranking.PERIODS:
        period = "all"
    data = ranking.board(period, _page_number(request.GET.get("page")))
    user = request.user
    for row in data["podium"] + data["rows"]:
        row["is_me"] = row["id"] == user.pk
    my_rank = ranking.rank_of(user, period)
    me = None
    if ranking.is_ranked(user):
        from courses.models import CourseProgress
        me = {
            "rank": my_rank,
            "xp": ranking.score_of(user, period),
            "courses": CourseProgress.objects.filter(user=user).values("course").distinct().count(),
            "username": user.username,
            "initial": (user.username[:1] or "?").upper(),
            "avatar_url": reverse("accounts:profile_photo", args=[user.pk]) if user.profile_picture else "",
            "on_page": any(row["is_me"] for row in data["podium"] + data["rows"]),
        }
    return render(request, "leaderboard/leaderboard.html", {
        "period": period,
        "tabs": [{"key": key, "label": ranking.PERIOD_LABELS[key]} for key in ranking.PERIODS],
        "period_label": ranking.period_label(period),
        "board": data,
        "podium": data["podium"],
        "rows": data["rows"],
        "my_rank": my_rank,
        "me": me,
        "is_staff_account": user.is_staff or user.is_superuser,
        "page_numbers": range(1, data["pages"] + 1),
    })
