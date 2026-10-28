"""Mission timing analytics from finished GameAttempt rows."""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median

from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.utils import timezone

from games.attempts import qualifying_percent
from games.models import GameAttempt
from games.registry import GAMES_REGISTRY

PAGE_SIZE = 15
FAST_MARK_SECONDS = 30


def _parse_date(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _percent(score, total) -> int:
    if not total:
        return 0
    return round(score / total * 100)


def _names():
    """Every mission, including Coming Soon ones, so past attempts stay in the report."""
    return {game["key"]: game.get("card_name") or game["name"] for game in GAMES_REGISTRY}


def mission_analytics_report(params) -> dict:
    from games.attempts import finalize_expired_attempts

    finalize_expired_attempts(limit=100)
    names = _names()
    keys = list(names)
    mission = params.get("mission") or ""
    if mission not in names:
        mission = ""
    start = _parse_date(params.get("start") or "")
    end = _parse_date(params.get("end") or "")
    if start and end and end < start:
        start, end = end, start
    sort = params.get("sort") or "duration"
    if sort not in {"duration", "score", "date"}:
        sort = "duration"
    view = params.get("view") or "qualifying"
    if view not in {"qualifying", "best", "all"}:
        view = "qualifying"
    query = (params.get("q") or "").strip()
    try:
        page_number = int(params.get("page") or 1)
    except (TypeError, ValueError):
        page_number = 1

    qs = GameAttempt.objects.finished().filter(
        user__is_staff=False,
        user__is_superuser=False,
        game_key__in=keys,
        total_questions__gt=0,
    ).select_related("user")
    if mission:
        qs = qs.filter(game_key=mission)
    if start:
        qs = qs.filter(completed_at__date__gte=start)
    if end:
        qs = qs.filter(completed_at__date__lte=end)
    if query:
        qs = qs.filter(
            Q(user__username__icontains=query)
            | Q(user__full_name__icontains=query)
            | Q(user__email__icontains=query)
        )

    completed = qs.filter(status=GameAttempt.STATUS_COMPLETED).count()
    timed_out = qs.filter(status=GameAttempt.STATUS_TIMED_OUT).count()
    finished = completed + timed_out
    threshold = qualifying_percent()
    timed_rows = qs.filter(
        status=GameAttempt.STATUS_COMPLETED,
        elapsed_seconds__isnull=False,
    )
    durations = list(timed_rows.values_list("elapsed_seconds", flat=True))
    score_avg = qs.aggregate(
        v=Avg("score"),
    )["v"]
    percent_values = [
        _percent(score, total)
        for score, total in qs.values_list("score", "total_questions")
    ]
    average_score = round(sum(percent_values) / len(percent_values)) if percent_values else None

    summary = {
        "completed": completed,
        "timed_out": timed_out,
        "finished": finished,
        "average_time": round(sum(durations) / len(durations)) if durations else None,
        "median_time": round(median(durations)) if durations else None,
        "average_score": average_score,
        "completion_rate": round(completed / finished * 100) if finished else None,
        "timeout_rate": round(timed_out / finished * 100) if finished else None,
        "learners": qs.values("user_id").distinct().count(),
        "timed_records": len(durations),
        "historical_without_time": completed - len(durations),
        "threshold": threshold,
        "fast_mark": FAST_MARK_SECONDS,
    }

    charts = _charts(qs, names, keys, start, end, mission, threshold)
    board, page = _leaderboard(qs, names, threshold, sort, view, page_number)
    fastest, highest = _callouts(qs, names, threshold)
    return {
        "summary": summary,
        "charts": charts,
        "leaderboard": board,
        "page": page,
        "fastest": fastest,
        "highest": highest,
        "filters": {
            "mission": mission,
            "start": start.isoformat() if start else "",
            "end": end.isoformat() if end else "",
            "sort": sort,
            "view": view,
            "q": query,
        },
        "missions": [{"key": key, "name": names[key]} for key in keys],
        "mission_label": names.get(mission, "All playable missions"),
    }


def _charts(qs, names, keys, start, end, mission, threshold):
    by_mission = []
    grouped = {
        row["game_key"]: row
        for row in qs.values("game_key").annotate(
            completed=Count("id", filter=Q(status=GameAttempt.STATUS_COMPLETED)),
            timed_out=Count("id", filter=Q(status=GameAttempt.STATUS_TIMED_OUT)),
            avg_time=Avg("elapsed_seconds", filter=Q(
                status=GameAttempt.STATUS_COMPLETED,
                elapsed_seconds__isnull=False,
            )),
        )
    }
    for key in keys:
        row = grouped.get(key) or {}
        by_mission.append({
            "key": key,
            "name": names[key],
            "completed": row.get("completed") or 0,
            "timed_out": row.get("timed_out") or 0,
            "avg_time": round(row["avg_time"]) if row.get("avg_time") is not None else None,
        })

    scatter = []
    for attempt in qs.filter(elapsed_seconds__isnull=False).order_by("-completed_at")[:300]:
        percent = attempt.percent
        scatter.append({
            "x": attempt.elapsed_seconds,
            "y": percent,
            "mission": names.get(attempt.game_key, attempt.game_key),
            "learner": attempt.user.display_name(),
            "fast": attempt.elapsed_seconds <= FAST_MARK_SECONDS,
            "high": percent >= threshold,
            "timeout": attempt.status == GameAttempt.STATUS_TIMED_OUT,
        })

    activity = _activity(qs.filter(status=GameAttempt.STATUS_COMPLETED), start, end)
    qualifying = _qualifying_rows(qs, threshold)
    fastest = sorted(qualifying, key=lambda row: (row.elapsed_seconds, -row.score, row.id))
    if mission:
        leaders = fastest
    else:
        leaders = fastest
    seen = set()
    top = []
    for attempt in leaders:
        if attempt.user_id in seen:
            continue
        seen.add(attempt.user_id)
        top.append({
            "learner": attempt.user.display_name(),
            "mission": names.get(attempt.game_key, attempt.game_key),
            "seconds": attempt.elapsed_seconds,
            "percent": attempt.percent,
        })
        if len(top) == 8:
            break
    return {
        "by_mission": by_mission,
        "scatter": scatter,
        "activity": activity,
        "leaders": top,
        "threshold": threshold,
        "fast_mark": FAST_MARK_SECONDS,
    }


def _activity(completed_qs, start, end):
    rows = list(
        completed_qs.exclude(completed_at__isnull=True)
        .values_list("completed_at", flat=True)
    )
    if not rows:
        return []
    days = {}
    for stamp in rows:
        local = timezone.localtime(stamp).date()
        days[local] = days.get(local, 0) + 1
    first = start or min(days)
    last = end or max(days)
    span = (last - first).days
    weekly = span > 45
    buckets = {}
    cursor = first
    while cursor <= last:
        key = cursor - timedelta(days=cursor.weekday()) if weekly else cursor
        buckets.setdefault(key, 0)
        cursor += timedelta(days=1)
    for day, count in days.items():
        if day < first or day > last:
            continue
        key = day - timedelta(days=day.weekday()) if weekly else day
        buckets[key] = buckets.get(key, 0) + count
    return [
        {"label": key.isoformat(), "count": buckets[key]}
        for key in sorted(buckets)
    ]


def _qualifying_rows(qs, threshold):
    rows = []
    for attempt in qs.filter(status=GameAttempt.STATUS_COMPLETED, elapsed_seconds__isnull=False):
        if attempt.percent >= threshold:
            rows.append(attempt)
    return rows


def _callouts(qs, names, threshold):
    rows = _qualifying_rows(qs, threshold)
    if not rows:
        return None, None
    fastest = min(rows, key=lambda row: (row.elapsed_seconds, -row.score, row.id))
    highest = max(rows, key=lambda row: (row.score / row.total_questions, -row.elapsed_seconds, -row.id))

    def pack(attempt, label):
        return {
            "label": label,
            "learner": attempt.user.display_name(),
            "mission": names.get(attempt.game_key, attempt.game_key),
            "seconds": attempt.elapsed_seconds,
            "percent": attempt.percent,
            "correct": attempt.score,
            "total": attempt.total_questions,
            "when": attempt.completed_at,
        }

    return pack(fastest, "Fastest qualifying"), pack(highest, "Highest qualifying score")


def _leaderboard(qs, names, threshold, sort, view, page_number):
    if view == "all":
        rows = list(qs.exclude(completed_at__isnull=True))
    else:
        rows = _qualifying_rows(qs, threshold)
        if view == "best":
            rows.sort(key=lambda row: (-row.score, row.elapsed_seconds or 10**9, row.id))
            seen = set()
            best = []
            for row in rows:
                if row.user_id in seen:
                    continue
                seen.add(row.user_id)
                best.append(row)
            rows = best

    def sort_key(row):
        elapsed = row.elapsed_seconds if row.elapsed_seconds is not None else 10**9
        when = row.completed_at or timezone.now()
        if sort == "score":
            return (-row.percent, elapsed, when, row.id)
        if sort == "date":
            return (-when.timestamp(), elapsed, -row.percent, row.id)
        return (elapsed, -row.percent, when, row.id)

    rows.sort(key=sort_key)
    paginator = Paginator(rows, PAGE_SIZE)
    page = paginator.get_page(page_number)
    start_rank = page.start_index()
    board = []
    for offset, attempt in enumerate(page.object_list):
        board.append({
            "rank": start_rank + offset,
            "learner": attempt.user.display_name(),
            "mission": names.get(attempt.game_key, attempt.game_key),
            "seconds": attempt.elapsed_seconds,
            "percent": attempt.percent,
            "correct": attempt.score,
            "total": attempt.total_questions,
            "when": attempt.completed_at,
            "status": attempt.get_status_display(),
            "attempt_id": attempt.pk,
        })
    return board, page
