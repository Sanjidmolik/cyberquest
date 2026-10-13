"""
Mission-attempt review for the Admin Command Center.

Every filter, sort, count and page is computed by the database; only the
rows of the current page are loaded. Nothing here writes or invents data:
values the server never recorded (for example timing on attempts made
before the mission timer existed) are shown as missing.

Outcome is derived from what GameAttempt actually stores:

  completed   status=completed (submitted before the deadline)
  timed_out   status=timed_out, submitted after the deadline passed
  abandoned   status=timed_out closed by the server with no submission
              (submission_method=expiry), or still in progress past its
              deadline and not yet closed
  active      status=in_progress and the deadline has not passed
"""

from __future__ import annotations

from datetime import datetime

from django.core.paginator import Paginator
from django.db.models import Case, Count, F, FloatField, Q, Value, When
from django.db.models.functions import Cast, Coalesce
from django.utils import timezone

from games.attempts import METHOD_EXPIRY
from games.models import GameAttempt

PAGE_SIZE = 25
FINISHED = (GameAttempt.STATUS_COMPLETED, GameAttempt.STATUS_TIMED_OUT)

OUTCOMES = (
    ("completed", "Completed"),
    ("timed_out", "Timed out"),
    ("abandoned", "Abandoned"),
    ("active", "Active"),
)
OUTCOME_LABELS = dict(OUTCOMES)

SORTS = {
    "newest": ("Newest first", [F("began").desc(nulls_last=True), F("id").desc()]),
    "oldest": ("Oldest first", [F("began").asc(nulls_last=True), F("id").asc()]),
    "fastest": ("Fastest", [F("elapsed_seconds").asc(nulls_last=True), F("id").desc()]),
    "slowest": ("Slowest", [F("elapsed_seconds").desc(nulls_last=True), F("id").desc()]),
    "accuracy_high": ("Highest accuracy", [F("accuracy").desc(nulls_last=True), F("id").desc()]),
    "accuracy_low": ("Lowest accuracy", [F("accuracy").asc(nulls_last=True), F("id").desc()]),
    "learner": ("Learner A–Z", [F("user__username").asc(nulls_last=True), F("user__email").asc(), F("id").desc()]),
    "mission": ("Mission A–Z", [F("game_key").asc(), F("id").desc()]),
}


def _outcome_q(outcome: str, now) -> Q:
    expired_open = Q(status=GameAttempt.STATUS_IN_PROGRESS, deadline_at__lte=now)
    if outcome == "completed":
        return Q(status=GameAttempt.STATUS_COMPLETED)
    if outcome == "timed_out":
        return Q(status=GameAttempt.STATUS_TIMED_OUT) & ~Q(submission_method=METHOD_EXPIRY)
    if outcome == "abandoned":
        return Q(status=GameAttempt.STATUS_TIMED_OUT, submission_method=METHOD_EXPIRY) | expired_open
    if outcome == "active":
        return Q(status=GameAttempt.STATUS_IN_PROGRESS) & ~expired_open
    return Q()


def outcome_of(attempt, now) -> str:
    if attempt.status == GameAttempt.STATUS_COMPLETED:
        return "completed"
    if attempt.status == GameAttempt.STATUS_TIMED_OUT:
        return "abandoned" if attempt.submission_method == METHOD_EXPIRY else "timed_out"
    if attempt.deadline_at and attempt.deadline_at <= now:
        return "abandoned"
    return "active"


def _date(value):
    try:
        return datetime.strptime((value or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _int(value, low, high):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high else None


def parse_filters(params) -> dict:
    mission_keys = {key for key, _ in GameAttempt.GAME_CHOICES}
    start, end = _date(params.get("start")), _date(params.get("end"))
    if start and end and end < start:
        start, end = end, start
    min_acc, max_acc = _int(params.get("min_accuracy"), 0, 100), _int(params.get("max_accuracy"), 0, 100)
    if min_acc is not None and max_acc is not None and max_acc < min_acc:
        min_acc, max_acc = max_acc, min_acc
    min_dur, max_dur = _int(params.get("min_seconds"), 0, 86400), _int(params.get("max_seconds"), 0, 86400)
    if min_dur is not None and max_dur is not None and max_dur < min_dur:
        min_dur, max_dur = max_dur, min_dur
    mission = params.get("mission") or ""
    outcome = params.get("outcome") or ""
    sort = params.get("sort") or "newest"
    return {
        "q": (params.get("q") or "").strip()[:100],
        "mission": mission if mission in mission_keys else "",
        "outcome": outcome if outcome in OUTCOME_LABELS else "",
        "start": start,
        "end": end,
        "min_accuracy": min_acc,
        "max_accuracy": max_acc,
        "min_seconds": min_dur,
        "max_seconds": max_dur,
        "sort": sort if sort in SORTS else "newest",
        "include_staff": params.get("include_staff") == "1",
    }


def filtered_attempts(filters: dict, now=None):
    now = now or timezone.now()
    qs = (
        GameAttempt.objects.select_related("user")
        # The answer map and question list are large and not shown here.
        .defer("answers", "selected_question_ids")
        .annotate(
            began=Coalesce("started_at", "completed_at"),
            # Only finished attempts have a final score to measure.
            accuracy=Case(
                When(total_questions__gt=0, status__in=FINISHED, then=Cast(F("score"), FloatField()) * Value(100.0)
                     / Cast(F("total_questions"), FloatField())),
                default=None,
                output_field=FloatField(),
            ),
        )
    )
    if not filters["include_staff"]:
        qs = qs.filter(user__is_staff=False, user__is_superuser=False)
    query = filters["q"]
    if query:
        match = (
            Q(user__username__icontains=query)
            | Q(user__full_name__icontains=query)
            | Q(user__email__icontains=query)
        )
        if query.isdigit():
            match |= Q(pk=int(query))
        qs = qs.filter(match)
    if filters["mission"]:
        qs = qs.filter(game_key=filters["mission"])
    if filters["outcome"]:
        qs = qs.filter(_outcome_q(filters["outcome"], now))
    if filters["start"]:
        qs = qs.filter(began__date__gte=filters["start"])
    if filters["end"]:
        qs = qs.filter(began__date__lte=filters["end"])
    if filters["min_accuracy"] is not None:
        qs = qs.filter(accuracy__gte=filters["min_accuracy"])
    if filters["max_accuracy"] is not None:
        qs = qs.filter(accuracy__lte=filters["max_accuracy"])
    if filters["min_seconds"] is not None:
        qs = qs.filter(elapsed_seconds__gte=filters["min_seconds"])
    if filters["max_seconds"] is not None:
        qs = qs.filter(elapsed_seconds__lte=filters["max_seconds"])
    return qs


def summary(qs, now) -> dict:
    """One aggregate query over the filtered set."""
    counts = qs.order_by().aggregate(
        total=Count("id"),
        **{key: Count("id", filter=_outcome_q(key, now)) for key, _ in OUTCOMES},
    )
    return counts


def _row(attempt, names, now) -> dict:
    outcome = outcome_of(attempt, now)
    finished = attempt.status in (GameAttempt.STATUS_COMPLETED, GameAttempt.STATUS_TIMED_OUT)
    total = attempt.total_questions
    return {
        "id": attempt.pk,
        "user": attempt.user,
        "mission": names.get(attempt.game_key, attempt.game_key),
        "started_at": attempt.started_at,
        "completed_at": attempt.completed_at if finished else None,
        "deadline_at": attempt.deadline_at,
        "elapsed_seconds": attempt.elapsed_seconds if finished else None,
        "score": attempt.score if finished else None,
        "total": total,
        "incorrect": (total - attempt.score) if finished and total else None,
        "accuracy": round(attempt.accuracy) if finished and attempt.accuracy is not None else None,
        "xp_awarded": attempt.xp_awarded if finished else None,
        "outcome": outcome,
        "outcome_label": OUTCOME_LABELS[outcome],
        "legacy": finished and attempt.started_at is None,
    }


def attempts_report(params, *, page_number=1) -> dict:
    now = timezone.now()
    filters = parse_filters(params)
    qs = filtered_attempts(filters, now)
    page = Paginator(qs.order_by(*SORTS[filters["sort"]][1]), PAGE_SIZE).get_page(page_number)
    names = dict(GameAttempt.GAME_CHOICES)
    return {
        "filters": filters,
        "page": page,
        "rows": [_row(attempt, names, now) for attempt in page.object_list],
        "summary": summary(qs, now),
        "missions": GameAttempt.GAME_CHOICES,
        "outcomes": OUTCOMES,
        "sorts": [(key, label) for key, (label, _) in SORTS.items()],
    }
