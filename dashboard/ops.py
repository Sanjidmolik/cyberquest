"""Read-only aggregations and safe operational actions for the superuser command center."""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, F, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from accounts.models import UserActivityDay
from achievements.models import Badge, UserBadge
from certificates.models import IssuedCertificate
from courses.models import Course, CourseProgress
from games.models import GameAttempt, Question, QuestionSet
from games.registry import GAMES_REGISTRY
from notifications.models import Notification
from pages.models import ContactMessage
from practice.models import PracticeSession
from question_bank.models import QuestionBank

User = get_user_model()

STUDENTS = Q(is_staff=False, is_superuser=False)


def students():
    return User.objects.filter(STUDENTS)


def _week_bounds():
    today = timezone.localdate()
    start = today - timedelta(days=6)
    prev = start - timedelta(days=7)
    return today, start, prev


def overview_kpis():
    today, start, prev = _week_bounds()
    start_dt = timezone.make_aware(datetime.combine(start, time.min))
    prev_dt = timezone.make_aware(datetime.combine(prev, time.min))

    total_students = students().count()
    new_students = students().filter(date_joined__gte=start_dt).count()
    prev_students = students().filter(date_joined__gte=prev_dt, date_joined__lt=start_dt).count()

    active = (
        UserActivityDay.objects.filter(day__gte=start, user__is_staff=False, user__is_superuser=False)
        .values("user").distinct().count()
    )
    published = Course.objects.filter(is_published=True).count()
    completions = CourseProgress.objects.filter(course__is_published=True, user__is_staff=False).count()
    possible = published * total_students
    completion_rate = round(completions / possible * 100) if possible else 0

    attempts = GameAttempt.objects.count()
    attempts_week = GameAttempt.objects.filter(completed_at__gte=start_dt).count()
    attempts_prev = GameAttempt.objects.filter(completed_at__gte=prev_dt, completed_at__lt=start_dt).count()

    practice_n = PracticeSession.objects.count()
    score_avg = (
        GameAttempt.objects.filter(total_questions__gt=0)
        .aggregate(v=Avg(F("score") * 100.0 / F("total_questions")))
        .get("v")
    )
    issued = IssuedCertificate.objects.count()
    review_banks = QuestionBank.objects.filter(status=QuestionBank.STATUS_REVIEW).count()
    open_contact = ContactMessage.objects.filter(is_resolved=False).count()

    return {
        "total_students": total_students,
        "new_students": new_students,
        "student_delta": new_students - prev_students,
        "active_students": active,
        "published_courses": published,
        "completion_rate": completion_rate,
        "completions": completions,
        "game_attempts": attempts,
        "attempt_delta": attempts_week - attempts_prev,
        "practice_sessions": practice_n,
        "mean_attempt_score": round(score_avg or 0),
        "certificates_issued": issued,
        "banks_in_review": review_banks,
        "open_contact": open_contact,
        "window_label": f"{start.isoformat()} – {today.isoformat()}",
    }


def recent_activity(limit=24):
    rows = []
    for user in students().order_by("-date_joined")[:8]:
        rows.append({
            "kind": "Registration",
            "who": user.display_name(),
            "detail": user.email,
            "when": user.date_joined,
            "status": "Active" if user.is_active else "Inactive",
        })
    for row in CourseProgress.objects.select_related("user", "course").order_by("-completed_at")[:8]:
        rows.append({
            "kind": "Course complete",
            "who": row.user.display_name(),
            "detail": row.course.code,
            "when": row.completed_at,
            "status": "Completed",
        })
    for row in GameAttempt.objects.select_related("user").order_by("-completed_at")[:8]:
        rows.append({
            "kind": "Game attempt",
            "who": row.user.display_name(),
            "detail": f"{row.game_key} {row.score}/{row.total_questions}",
            "when": row.completed_at,
            "status": f"{row.percent}%",
        })
    for row in UserBadge.objects.select_related("user", "badge").order_by("-earned_at")[:6]:
        rows.append({
            "kind": "Badge",
            "who": row.user.display_name(),
            "detail": row.badge.name,
            "when": row.earned_at,
            "status": "Earned",
        })
    for row in PracticeSession.objects.select_related("user").filter(status="completed").order_by("-completed_at")[:6]:
        rows.append({
            "kind": "Practice",
            "who": row.user.display_name(),
            "detail": f"{row.domain} {row.activity_type}",
            "when": row.completed_at or row.created_at,
            "status": f"{row.percent}%",
        })
    for row in IssuedCertificate.objects.select_related("user").order_by("-issued_at")[:6]:
        rows.append({
            "kind": "Certificate",
            "who": row.recipient_name,
            "detail": row.certificate_id,
            "when": row.issued_at,
            "status": "Issued",
        })
    for row in ContactMessage.objects.order_by("-submitted_at")[:6]:
        rows.append({
            "kind": "Contact",
            "who": row.name,
            "detail": row.email,
            "when": row.submitted_at,
            "status": "Resolved" if row.is_resolved else "Open",
        })
    rows.sort(key=lambda item: item["when"] or timezone.now(), reverse=True)
    return rows[:limit]


def signup_bars(days=14):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    start_dt = timezone.make_aware(datetime.combine(start, time.min))
    counts = {}
    for row in (
        students().filter(date_joined__gte=start_dt)
        .annotate(day=TruncDate("date_joined"))
        .values("day")
        .annotate(n=Count("id"))
    ):
        day = row["day"].date() if hasattr(row["day"], "hour") else row["day"]
        counts[day] = row["n"]
    peak = max(counts.values(), default=0) or 1
    bars = []
    cursor = start
    while cursor <= today:
        n = counts.get(cursor, 0)
        bars.append({"label": cursor.strftime("%m-%d"), "n": n, "height": round(n / peak * 100)})
        cursor += timedelta(days=1)
    return bars


def course_rows():
    published_ids = Course.objects.filter(is_published=True)
    progress = (
        CourseProgress.objects.filter(course__in=published_ids)
        .values("course_id")
        .annotate(done=Count("id"), learners=Count("user", distinct=True))
    )
    by_id = {row["course_id"]: row for row in progress}
    reading = (
        Course.objects.filter(is_published=True)
        .annotate(readers=Count("reading_progress", distinct=True))
    )
    student_n = students().count() or 1
    rows = []
    for course in reading.order_by("order", "code"):
        stats = by_id.get(course.id, {})
        done = stats.get("done", 0)
        rows.append({
            "course": course,
            "completed": done,
            "readers": course.readers,
            "percent": round(done / student_n * 100),
        })
    return rows


def game_rows():
    names = {g["key"]: g["name"] for g in GAMES_REGISTRY}
    grouped = (
        GameAttempt.objects.filter(total_questions__gt=0).values("game_key")
        .annotate(
            attempts=Count("id"),
            players=Count("user", distinct=True),
            avg_score=Avg(F("score") * 100.0 / F("total_questions")),
        )
        .order_by("-attempts")
    )
    rows = []
    for row in grouped:
        if not row["game_key"]:
            continue
        rows.append({
            "key": row["game_key"],
            "name": names.get(row["game_key"], row["game_key"]),
            "attempts": row["attempts"],
            "players": row["players"],
            "avg_score": round(row["avg_score"] or 0),
        })
    return rows


def practice_rows():
    rows = (
        PracticeSession.objects.values("domain")
        .annotate(
            sessions=Count("id"),
            completed=Count("id", filter=Q(status="completed")),
            players=Count("user", distinct=True),
            avg_score=Avg("score", filter=Q(status="completed")),
        )
        .order_by("domain")
    )
    return [
        {
            "domain": row["domain"],
            "sessions": row["sessions"],
            "completed": row["completed"],
            "players": row["players"],
            "rate": round(row["completed"] / row["sessions"] * 100) if row["sessions"] else 0,
            "avg_score": round(row["avg_score"] or 0),
        }
        for row in rows
    ]


def question_summary():
    return {
        "banks": QuestionBank.objects.count(),
        "review": QuestionBank.objects.filter(status=QuestionBank.STATUS_REVIEW).count(),
        "approved": QuestionBank.objects.filter(status=QuestionBank.STATUS_APPROVED).count(),
        "failed": QuestionBank.objects.filter(status=QuestionBank.STATUS_FAILED).count(),
        "questions": Question.objects.count(),
        "ai": Question.objects.filter(generated_by_ai=True).count(),
        "edited": Question.objects.filter(manually_edited=True).count(),
        "sets_review": QuestionSet.objects.filter(status=QuestionSet.STATUS_REVIEW).count(),
        "sets_approved": QuestionSet.objects.filter(status=QuestionSet.STATUS_APPROVED).count(),
        "sets_rejected": QuestionSet.objects.filter(status=QuestionSet.STATUS_REJECTED).count(),
    }
