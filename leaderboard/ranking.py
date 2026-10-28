"""Who is ranked, by what score, and in which order. Used by the leaderboard page, the
dashboard's own-rank line and the Command Center leaderboard, so all three agree.

- Ranked: active accounts with a username, except staff and superusers.
- All-time score: `user.xp`. Week / month score: XP granted in that period by the records
  that grant it (missions, practice attempts, older practice sessions). Manual adjustments
  to `user.xp` leave no record, so they count only in All-time.
- Ties share a rank (1, 2, 2, 4); whoever reached the score first is listed first.
- Weeks start on Saturday; boundaries use settings.TIME_ZONE.
"""

from datetime import datetime, time, timedelta, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Case, Count, F, IntegerField, OuterRef, Subquery, Sum, Value, When, Window
from django.db.models.functions import Coalesce, Greatest, Rank
from django.utils import timezone

from accounts.public import avatar_url

PERIODS = ("all", "month", "week")
PERIOD_LABELS = {"all": "All-time", "month": "This month", "week": "This week"}
WEEK_START = 5          # Saturday (date.weekday(): Monday is 0)
PAGE_SIZE = 25
PODIUM = 3
CACHE_SECONDS = 60
# Stands in for "no XP record" when finding the latest grant (any real grant is later).
NO_GRANT = datetime(1970, 1, 1, tzinfo=dt_timezone.utc)


def eligible_users():
    return (
        get_user_model().objects.filter(is_active=True, is_staff=False, is_superuser=False)
        .exclude(username__isnull=True).exclude(username="")
    )


def is_ranked(user):
    return bool(user.is_active and not user.is_staff and not user.is_superuser and user.username)


def period_bounds(period, now=None):
    """(start, end) as aware datetimes in settings.TIME_ZONE, or (None, None) for all-time."""
    if period == "all":
        return None, None
    today = timezone.localdate(now)
    if period == "week":
        first = today - timedelta(days=(today.weekday() - WEEK_START) % 7)
        last = first + timedelta(days=7)
    else:
        first = today.replace(day=1)
        last = (first + timedelta(days=32)).replace(day=1)
    zone = timezone.get_current_timezone()
    return (timezone.make_aware(datetime.combine(first, time.min), zone),
            timezone.make_aware(datetime.combine(last, time.min), zone))


def period_label(period, now=None):
    """'This week: 25–31 Oct', 'This month: Oct 2026', or 'All-time'."""
    start, end = period_bounds(period, now)
    if start is None:
        return PERIOD_LABELS["all"]
    if period == "month":
        return f"This month: {start:%b %Y}"
    first, last = timezone.localtime(start).date(), timezone.localtime(end).date() - timedelta(days=1)
    span = (f"{first.day}–{last.day} {last:%b}" if first.month == last.month
            else f"{first.day} {first:%b} – {last.day} {last:%b}")
    return f"This week: {span}"


def _xp_sources():
    from games.models import GameAttempt
    from practice.models import Attempt, PracticeSession
    return (
        (GameAttempt.objects.all(), "completed_at"),
        (Attempt.objects.real(), "finished_at"),                 # previews award nothing
        (PracticeSession.objects.filter(status="completed"), "completed_at"),
    )


def _grants(qs, when, start, end):
    qs = qs.filter(user=OuterRef("pk"), xp_awarded__gt=0)
    if start is not None:
        qs = qs.filter(**{f"{when}__gte": start, f"{when}__lt": end})
    return qs.order_by()


def scored(period="all", now=None):
    """Every ranked user with `score`, `reached` (when the score was reached) and `courses`
    (completed courses). Week and month leave out users with no XP in the period."""
    from courses.models import CourseProgress

    start, end = period_bounds(period, now)
    sums, latest = [], []
    for qs, when in _xp_sources():
        grants = _grants(qs, when, start, end)
        sums.append(Coalesce(Subquery(grants.values("user").annotate(s=Sum("xp_awarded")).values("s")[:1],
                                      output_field=IntegerField()), Value(0)))
        latest.append(Coalesce(Subquery(grants.order_by(f"-{when}").values(when)[:1]), Value(NO_GRANT)))
    courses = Subquery(CourseProgress.objects.filter(user=OuterRef("pk")).order_by().values("user")
                       .annotate(c=Count("course", distinct=True)).values("c")[:1], output_field=IntegerField())
    # When the score was reached: the latest XP grant counted, or the join date if none is recorded.
    qs = eligible_users().annotate(courses=Coalesce(courses, Value(0)), last_grant=Greatest(*latest)).annotate(
        reached=Case(When(last_grant=NO_GRANT, then=F("date_joined")), default=F("last_grant")))
    if period == "all":
        qs = qs.annotate(score=F("xp"))
    else:
        qs = qs.annotate(score=sums[0] + sums[1] + sums[2]).filter(score__gt=0)
    return qs


def ranked(period="all", now=None):
    """scored() plus `board_rank` (ties share a rank), in leaderboard order."""
    return scored(period, now).annotate(
        board_rank=Window(Rank(), order_by=F("score").desc()),
    ).order_by("-score", "reached", "pk")


def score_of(user, period="all", now=None):
    if period == "all":
        return user.xp
    row = scored(period, now).filter(pk=user.pk).values("score").first() if is_ranked(user) else None
    return row["score"] if row else 0


def rank_of(user, period="all", now=None):
    """The user's rank (ties shared), or None if they aren't ranked in this period."""
    if not is_ranked(user):
        return None
    score = score_of(user, period, now)
    if period != "all" and score <= 0:
        return None
    if period == "all":
        return eligible_users().filter(xp__gt=score).count() + 1
    return scored(period, now).filter(score__gt=score).count() + 1


def _row(user):
    return {
        "id": user.pk,
        "rank": user.board_rank,
        "username": user.username,
        "initial": (user.username[:1] or "?").upper(),
        "avatar_url": avatar_url(user),             # random token; default image if no photo
        "courses": user.courses,
        "xp": user.score,
    }


def board(period="all", page=1, now=None):
    """{'podium': [...], 'rows': [...], 'total', 'pages', 'page'}; rows are plain dicts of
    public fields only. Cached for 60 s per period window and page."""
    start, _ = period_bounds(period, now)
    page = max(1, int(page))
    key = f"leaderboard:v2:{period}:{start.date().isoformat() if start else 'all'}:{page}"
    data = cache.get(key)
    if data is None:
        qs = ranked(period, now).only("pk", "username", "avatar_token", "xp", "date_joined")
        total = qs.count()
        rest = max(0, total - PODIUM)
        pages = max(1, -(-rest // PAGE_SIZE))
        page = min(page, pages)
        offset = PODIUM + (page - 1) * PAGE_SIZE
        data = {
            "podium": [_row(u) for u in qs[:PODIUM]],
            "rows": [_row(u) for u in qs[offset:offset + PAGE_SIZE]],
            "total": total, "pages": pages, "page": page,
        }
        cache.set(key, data, CACHE_SECONDS)
    return data
