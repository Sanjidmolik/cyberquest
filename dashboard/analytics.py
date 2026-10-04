"""Staff analytics built from existing user, activity, and GameAttempt rows."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import UserActivityDay
from games.models import GameAttempt
from games.registry import GAMES_REGISTRY

User = get_user_model()


def _days(raw: str) -> int:
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return 30
    return days if days in {7, 30, 90} else 30


def analytics_payload(days: int) -> dict:
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    start_dt = timezone.make_aware(datetime.combine(start, time.min))

    signup_rows = (
        User.objects.filter(date_joined__gte=start_dt)
        .annotate(day=TruncDate("date_joined"))
        .values("day")
        .annotate(n=Count("id"))
    )
    signups = {}
    for row in signup_rows:
        day = row["day"]
        if hasattr(day, "hour"):
            day = day.date()
        signups[day] = row["n"]
    active = {
        row["day"]: row["n"]
        for row in (
            UserActivityDay.objects.filter(day__gte=start)
            .values("day")
            .annotate(n=Count("user", distinct=True))
        )
    }
    timeline = []
    peak_signups = max(signups.values(), default=0) or 1
    peak_active = max(active.values(), default=0) or 1
    cursor = start
    while cursor <= today:
        signup_n = signups.get(cursor, 0)
        active_n = active.get(cursor, 0)
        timeline.append({
            "date": cursor.isoformat(),
            "signups": signup_n,
            "active_users": active_n,
            "signup_height": round(signup_n / peak_signups * 80),
            "active_height": round(active_n / peak_active * 80),
        })
        cursor += timedelta(days=1)

    names = {g["key"]: g["name"] for g in GAMES_REGISTRY}
    attempt_rows = (
        GameAttempt.objects.filter(completed_at__gte=start_dt)
        .values("game_key")
        .annotate(attempts=Count("id"), players=Count("user", distinct=True))
    )
    by_key = {row["game_key"]: row for row in attempt_rows}
    keys = list(dict.fromkeys([*names.keys(), *by_key.keys()]))
    courses = []
    for key in keys:
        row = by_key.get(key) or {}
        courses.append({
            "key": key,
            "name": names.get(key, key),
            "attempts": row.get("attempts", 0),
            "players": row.get("players", 0),
        })
    courses.sort(key=lambda item: item["attempts"], reverse=True)

    return {
        "days": days,
        "start": start.isoformat(),
        "end": today.isoformat(),
        "total_users": User.objects.count(),
        "active_definition": (
            "An active user is a distinct account with a recorded authenticated "
            "session day (login) on that date. Registered users are not counted as active."
        ),
        "active_users_in_range": UserActivityDay.objects.filter(day__gte=start).values("user").distinct().count(),
        "timeline": timeline,
        "courses": courses,
        "course_metric": "completed game attempts (one GameAttempt row each)",
    }
