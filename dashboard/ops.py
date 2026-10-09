"""Read-only aggregations and safe operational actions for the superuser command center."""

import os
from datetime import datetime, time, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import connection
from django.db.models import Avg, Count, F, IntegerField, Max, Min, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from accounts.models import UserActivityDay
from achievements.models import Badge, UserBadge
from certificates.eligibility import (
    REQUIRED_GAME_COUNT,
    REQUIRED_GAME_KEYS,
    get_eligibility_status,
    is_eligible_for_certificate,
)
from certificates.models import IssuedCertificate
from certificates.services.qr import build_verification_url
from courses.models import Course, CourseProgress, ReadingProgress
from courses.progress import server_total_pages
from games.game_config import GAME_QUESTION_CONFIG
from games.models import SET_COURSES, SET_COURSE_KEYS, GameAttempt, Question, QuestionSet
from games.quiz_data import QUIZ_GAMES
from games.registry import GAMES_REGISTRY
from games.stats import get_best_attempt_percentages
from games.views import XP_PER_CORRECT_ANSWER
from question_bank.services.selection import (
    approved_question_pool,
    latest_approved_bank,
    resolve_attempt_config,
)
from notifications.models import Notification
from notifications.utils import notify
from pages.models import ContactMessage
from practice.adaptive import get_cyber_dna
from practice.models import PracticeSession
from practice.scenarios import DOMAINS, SCENARIOS, get_scenario
from question_bank.models import QuestionBank

User = get_user_model()

STUDENTS = Q(is_staff=False, is_superuser=False)


def students():
    return User.objects.filter(STUDENTS)


def student_summary():
    """Directory totals for real student accounts. Staff are excluded."""
    row = students().aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(is_active=True)),
        avg_level=Avg("level"),
        avg_xp=Avg("xp"),
    )
    return {
        "total": row["total"] or 0,
        "active": row["active"] or 0,
        "avg_level": round(row["avg_level"] or 0),
        "avg_xp": round(row["avg_xp"] or 0),
    }


def student_levels():
    return list(students().order_by("level").values_list("level", flat=True).distinct())


def student_directory(query="", status="", level="", activity=""):
    """Filtered student list. Unknown status, level, or activity values are ignored by the caller."""
    qs = students().annotate(
        course_done=Count(
            "course_progress",
            filter=Q(course_progress__course__is_published=True),
            distinct=True,
        ),
    )
    needle = (query or "").strip()
    if needle:
        qs = qs.filter(
            Q(email__icontains=needle)
            | Q(username__icontains=needle)
            | Q(full_name__icontains=needle)
        )
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    if level != "" and str(level).isdigit():
        qs = qs.filter(level=int(level))
    if activity == "recent":
        start = timezone.localdate() - timedelta(days=6)
        qs = qs.filter(last_active_date__gte=start)
    elif activity == "never":
        qs = qs.filter(last_active_date__isnull=True)
    return qs.order_by("-date_joined", "-id")


def set_student_active(user, active):
    """Toggle the existing sign-in flag. Does not touch credentials or progress."""
    if user.is_active == active:
        return False
    user.is_active = active
    user.save(update_fields=["is_active"])
    return True


def ranked_accounts():
    """Accounts the student leaderboard ranks: active, and a username was chosen."""
    return (
        User.objects.filter(is_active=True)
        .exclude(username__isnull=True)
        .exclude(username="")
    )


def leaderboard_summary():
    """Overall totals for the ranked accounts. Filters do not change these figures."""
    stats = ranked_accounts().aggregate(total=Count("id"), highest=Max("xp"), average=Avg("xp"))
    average = stats["average"]
    return {
        "total": stats["total"],
        "highest": stats["highest"] or 0,
        "average": round(average) if average is not None else 0,
    }


def leaderboard_directory(query="", level="", activity=""):
    """
    Overall rank is the position in the student leaderboard order.
    Equal XP keeps the earlier account ahead so the page stays stable.
    Search and filters narrow the rows and leave those ranks in place.
    """
    ahead = (
        ranked_accounts()
        .filter(Q(xp__gt=OuterRef("xp")) | Q(xp=OuterRef("xp"), pk__lt=OuterRef("pk")))
        .order_by()
        .values("is_active")
        .annotate(c=Count("pk"))
        .values("c")
    )
    qs = ranked_accounts().annotate(
        board_rank=Coalesce(Subquery(ahead, output_field=IntegerField()), Value(0)) + Value(1)
    )
    needle = (query or "").strip()
    if needle:
        qs = qs.filter(
            Q(username__icontains=needle)
            | Q(full_name__icontains=needle)
            | Q(email__icontains=needle)
        )
    if level != "" and str(level).isdigit():
        qs = qs.filter(level=int(level))
    if activity == "recent":
        start = timezone.localdate() - timedelta(days=6)
        qs = qs.filter(last_active_date__gte=start)
    elif activity == "never":
        qs = qs.filter(last_active_date__isnull=True)
    return qs.order_by("board_rank", "id")


def notification_summary():
    """Platform totals. Viewing this screen does not change read state."""
    stats = Notification.objects.aggregate(
        total=Count("id"),
        unread=Count("id", filter=Q(is_read=False)),
    )
    total = stats["total"]
    unread = stats["unread"]
    return {"total": total, "unread": unread, "read": total - unread}


def notification_directory(query="", status="", window=""):
    qs = Notification.objects.select_related("user").order_by("-created_at", "-id")
    needle = (query or "").strip()
    if needle:
        qs = qs.filter(
            Q(message__icontains=needle)
            | Q(user__email__icontains=needle)
            | Q(user__username__icontains=needle)
            | Q(user__full_name__icontains=needle)
        )
    if status == "unread":
        qs = qs.filter(is_read=False)
    elif status == "read":
        qs = qs.filter(is_read=True)
    if window in ("7", "30"):
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=int(window)))
    return qs


def send_student_notification(email, message, link, request):
    """
    Create one in-app notification through notify().
    Returns (notification, field_errors). Success is only a saved row.
    This does not send email.
    """
    errors = {}
    raw_email = (email or "").strip()
    text = (message or "").strip()
    target = (link or "").strip()
    student = None
    if not raw_email:
        errors["email"] = "Enter the student's email address."
    elif "," in raw_email or " " in raw_email:
        errors["email"] = "Enter one student email address."
    else:
        student = students().filter(email__iexact=raw_email).first()
        if student is None:
            errors["email"] = "No student account uses that email."
    if not text:
        errors["message"] = "Enter a notification message."
    elif len(text) > 255:
        errors["message"] = "Keep the notification under 255 characters."
    if len(target) > 200 or (
        target
        and not url_has_allowed_host_and_scheme(
            url=target,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        )
    ):
        errors["link_url"] = "Notification links must stay on this site."
    if errors:
        return None, errors
    note = notify(student, text, target)
    if note is None or not getattr(note, "pk", None):
        return None, {"message": "The notification could not be saved."}
    return note, {}


def _xp_snapshot(user):
    """Stored XP and level, plus the same 100-XP level bar the student dashboard shows."""
    into_level = user.xp % 100
    return {
        "xp": user.xp,
        "level": user.level,
        "into_level": into_level,
        "remaining": 100 - into_level,
    }


def student_learning(user):
    published = list(Course.objects.filter(is_published=True).order_by("order", "code"))
    completed = {
        row.course_id: row.completed_at
        for row in CourseProgress.objects.filter(user=user, course__is_published=True)
    }
    readings = {
        row.course_id: row
        for row in ReadingProgress.objects.filter(user=user, course__is_published=True)
    }
    courses = []
    percents = []
    started = 0
    for course in published:
        if course.id in completed:
            percent = 100
            state = "Completed"
            when = completed[course.id]
            started += 1
        elif course.id in readings:
            pages = server_total_pages(course) or 0
            reached = readings[course.id].last_page_index + 1
            percent = min(100, round(reached / pages * 100)) if pages else 0
            state = "In progress"
            when = readings[course.id].updated_at
            started += 1
        else:
            percent = 0
            state = "Not started"
            when = None
        percents.append(percent)
        courses.append({
            "code": course.code,
            "title": course.title,
            "state": state,
            "percent": percent,
            "when": when,
        })
    return {
        "published": len(published),
        "started": started,
        "completed": len(completed),
        "average": round(sum(percents) / len(percents)) if percents else 0,
        "courses": courses,
    }


def student_games(user):
    names = {game["key"]: game["name"] for game in GAMES_REGISTRY}
    qs = GameAttempt.objects.filter(user=user)
    summary = qs.aggregate(
        attempts=Count("id"),
        games=Count("game_key", distinct=True),
        avg_score=Avg("score"),
        avg_percent=Avg(
            F("score") * 100.0 / F("total_questions"),
            filter=Q(total_questions__gt=0),
        ),
        xp=Sum("xp_awarded"),
        latest=Max("completed_at"),
    )
    best = [
        {"name": names.get(key, key), "percent": percent}
        for key, percent in sorted(
            get_best_attempt_percentages(user).items(),
            key=lambda item: names.get(item[0], item[0]),
        )
    ]
    recent = []
    for row in qs.order_by("-completed_at", "-id")[:6]:
        recent.append({
            "kind": "Game",
            "detail": f"{names.get(row.game_key, row.game_key)} {row.score}/{row.total_questions}",
            "when": row.completed_at,
            "status": f"{row.percent}%",
        })
    return {
        "attempts": summary["attempts"] or 0,
        "games": summary["games"] or 0,
        "avg_score": round(summary["avg_score"] or 0),
        "avg_percent": round(summary["avg_percent"] or 0),
        "xp": summary["xp"] or 0,
        "latest": summary["latest"],
        "best": best,
        "recent": recent,
    }


def student_practice(user):
    qs = PracticeSession.objects.filter(user=user)
    summary = qs.aggregate(
        sessions=Count("id"),
        completed=Count("id", filter=Q(status="completed")),
        avg_score=Avg("score", filter=Q(status="completed")),
        latest=Max("created_at"),
    )
    labels = dict(PracticeSession.DOMAIN_CHOICES)
    domains = [
        {
            "label": labels.get(row["domain"], row["domain"]),
            "sessions": row["sessions"],
            "completed": row["completed"],
        }
        for row in qs.values("domain").annotate(
            sessions=Count("id"),
            completed=Count("id", filter=Q(status="completed")),
        ).order_by("domain")
    ]
    dna = get_cyber_dna(user)
    recent = []
    for row in qs.order_by("-created_at", "-id")[:6]:
        recent.append({
            "kind": "Practice",
            "detail": f"{labels.get(row.domain, row.domain)} {row.get_activity_type_display()}",
            "when": row.completed_at or row.created_at,
            "status": f"{row.percent}%" if row.status == "completed" else row.get_status_display(),
        })
    return {
        "sessions": summary["sessions"] or 0,
        "completed": summary["completed"] or 0,
        "avg_score": round(summary["avg_score"] or 0),
        "latest": summary["latest"],
        "domains": domains,
        "dna": {
            "overall": dna["overall"],
            "overall_level": dna["overall_level"],
            "domains": [
                {"label": row["full_label"], "percent": row["percent"], "level": row["level"]}
                for row in dna["domains"]
            ],
        },
        "recent": recent,
    }


def student_profile(user):
    learning = student_learning(user)
    games = student_games(user)
    practice = student_practice(user)
    badges = list(
        UserBadge.objects.filter(user=user).select_related("badge").order_by("-earned_at", "-id")
    )
    issued = IssuedCertificate.objects.filter(user=user).first()
    certificate = None
    if issued is not None:
        certificate = {
            "certificate_id": issued.certificate_id,
            "recipient_name": issued.recipient_name,
            "score": issued.score,
            "issued_at": issued.issued_at,
        }
    activity = []
    activity.extend(games["recent"])
    activity.extend(practice["recent"])
    for course in learning["courses"]:
        if course["state"] == "Completed" and course["when"]:
            activity.append({
                "kind": "Course",
                "detail": course["title"],
                "when": course["when"],
                "status": "Completed",
            })
    for row in badges[:6]:
        activity.append({
            "kind": "Achievement",
            "detail": row.badge.name,
            "when": row.earned_at,
            "status": "Earned",
        })
    if certificate is not None:
        activity.append({
            "kind": "Certificate",
            "detail": certificate["certificate_id"],
            "when": certificate["issued_at"],
            "status": "Issued",
        })
    activity.sort(key=lambda item: item["when"] or timezone.now(), reverse=True)
    return {
        "id": user.pk,
        "username": user.username or "",
        "name": user.full_name or "",
        "display_name": user.display_name(),
        "email": user.email,
        "is_active": user.is_active,
        "joined": user.date_joined,
        "last_active": user.last_active_date,
        "streak": user.current_streak,
        "cyber_class": user.get_cyber_class_display(),
        "skill_level": user.get_skill_level_display(),
        "xp_info": _xp_snapshot(user),
        "learning": learning,
        "games": games,
        "practice": practice,
        "badges": badges,
        "badge_count": len(badges),
        "certificate": certificate,
        "eligible": is_eligible_for_certificate(user),
        "activity": activity[:12],
    }


def _ready_certificates():
    """Public verification treats a stored PDF as an issued certificate."""
    return IssuedCertificate.objects.exclude(pdf_file="")


def certificate_summary():
    _, start, _ = _week_bounds()
    start_dt = timezone.make_aware(datetime.combine(start, time.min))
    ready = _ready_certificates()
    return {
        "issued": ready.count(),
        "recent": ready.filter(issued_at__gte=start_dt).count(),
    }


def certificate_directory(query="", window="", readiness=""):
    qs = IssuedCertificate.objects.select_related("user").order_by("-issued_at", "-id")
    needle = (query or "").strip()
    if needle:
        qs = qs.filter(
            Q(certificate_id__icontains=needle)
            | Q(recipient_name__icontains=needle)
            | Q(user__email__icontains=needle)
            | Q(user__username__icontains=needle)
            | Q(user__full_name__icontains=needle)
        )
    if window in ("7", "30"):
        qs = qs.filter(issued_at__gte=timezone.now() - timedelta(days=int(window)))
    if readiness == "ready":
        qs = qs.exclude(pdf_file="")
    elif readiness == "incomplete":
        qs = qs.filter(pdf_file="")
    return qs


def eligible_students_without_certificate():
    """
    Students who pass the existing eligibility helper and do not yet have a
    publicly verifiable certificate. The game-count query only narrows the set;
    the yes/no decision stays in is_eligible_for_certificate.
    """
    ready_ids = _ready_certificates().values_list("user_id", flat=True)
    played = (
        GameAttempt.objects.filter(
            user__is_staff=False,
            user__is_superuser=False,
            total_questions__gt=0,
            game_key__in=REQUIRED_GAME_KEYS,
        )
        .exclude(user_id__in=ready_ids)
        .values("user_id")
        .annotate(games=Count("game_key", distinct=True))
        .filter(games__gte=REQUIRED_GAME_COUNT)
    )
    user_ids = [row["user_id"] for row in played]
    waiting = []
    for user in students().filter(pk__in=user_ids).order_by("email"):
        if is_eligible_for_certificate(user):
            waiting.append(user)
    return waiting


def certificate_detail_context(certificate, request):
    ready = bool(certificate.pdf_file)
    status = get_eligibility_status(certificate.user)
    user = certificate.user
    return {
        "id": certificate.pk,
        "certificate_id": certificate.certificate_id,
        "recipient_name": certificate.recipient_name,
        "score": certificate.score,
        "issued_at": certificate.issued_at,
        "ready": ready,
        "verify_url": build_verification_url(certificate.certificate_id, request=request),
        "student_id": user.pk,
        "student_name": user.full_name or "",
        "username": user.username or "",
        "email": user.email,
        "can_issue": ready is False and not user.is_staff and not user.is_superuser and status["eligible"],
        "eligibility": status,
    }


STUDENT_AWARDS = Q(awarded_to__user__is_staff=False, awarded_to__user__is_superuser=False)


def achievement_summary():
    """Award totals for student accounts. Staff and superusers are excluded."""
    awards = UserBadge.objects.filter(user__is_staff=False, user__is_superuser=False)
    return {
        "badges": Badge.objects.count(),
        "holders": awards.values("user_id").distinct().count(),
        "awards": awards.count(),
        "students": students().count(),
    }


def achievement_directory(query="", status=""):
    qs = (
        Badge.objects.annotate(
            earned=Count("awarded_to", filter=STUDENT_AWARDS),
            latest=Max("awarded_to__earned_at", filter=STUDENT_AWARDS),
        )
        .order_by("name", "id")
    )
    needle = (query or "").strip()
    if needle:
        qs = qs.filter(Q(name__icontains=needle) | Q(description__icontains=needle))
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    return qs


def achievement_earners(badge):
    return (
        UserBadge.objects.filter(
            badge=badge,
            user__is_staff=False,
            user__is_superuser=False,
        )
        .select_related("user")
        .order_by("-earned_at", "-id")
    )


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


def contact_summary():
    """Inbox totals. Opening a message does not change its resolved flag."""
    stats = ContactMessage.objects.aggregate(
        total=Count("id"),
        open=Count("id", filter=Q(is_resolved=False)),
    )
    total = stats["total"]
    open_count = stats["open"]
    return {"total": total, "open": open_count, "resolved": total - open_count}


def contact_directory(query="", state="", window=""):
    qs = ContactMessage.objects.all().order_by("-submitted_at", "-id")
    needle = (query or "").strip()
    if needle:
        qs = qs.filter(
            Q(name__icontains=needle)
            | Q(email__icontains=needle)
            | Q(message__icontains=needle)
        )
    if state == "open":
        qs = qs.filter(is_resolved=False)
    elif state == "resolved":
        qs = qs.filter(is_resolved=True)
    if window in ("7", "30"):
        qs = qs.filter(submitted_at__gte=timezone.now() - timedelta(days=int(window)))
    return qs


def create_command_superuser(email, username, password, confirm):
    """
    Create one superuser with Django's password hasher.
    Privilege flags are set here, never from the request body.
    """
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    User = get_user_model()
    errors = {}
    raw_email = (email or "").strip()
    raw_username = (username or "").strip()
    try:
        validate_email(raw_email)
    except ValidationError:
        errors["email"] = "Enter a valid email address."
    else:
        if User.objects.filter(email__iexact=raw_email).exists():
            errors["email"] = "An account with this email already exists."
    if not raw_username:
        errors["username"] = "Enter a username."
    elif User.objects.filter(username__iexact=raw_username).exists():
        errors["username"] = "That username is already taken."
    if not password:
        errors["password"] = "Enter a password."
    elif password != confirm:
        errors["confirm"] = "Passwords do not match."
    else:
        try:
            validate_password(password)
        except ValidationError as exc:
            errors["password"] = " ".join(exc.messages)
    if errors:
        return None, errors
    user = User.objects.create_superuser(
        email=raw_email,
        password=password,
        username=raw_username,
        ethical_agreement=True,
        is_staff=True,
        is_superuser=True,
    )
    return user, {}


def set_contact_resolved(message, resolved):
    """Write the existing resolved flag. Does not send email or a notification."""
    if message.is_resolved == resolved:
        return False
    message.is_resolved = resolved
    message.save(update_fields=["is_resolved"])
    return True


def send_contact_reply(message, reply):
    """
    Email the address stored on the contact message.
    The contact row is not saved, and a failed delivery is not described as sent.
    """
    text = (reply or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return False, "Enter a reply before sending."
    if len(text) > 4000:
        return False, "Keep the reply under 4000 characters."
    recipient = (message.email or "").strip()
    try:
        validate_email(recipient)
    except ValidationError:
        return False, "This contact does not have an email address that can receive a reply."
    sender = (settings.DEFAULT_FROM_EMAIL or "").strip()
    if not sender:
        return False, "The reply could not be sent. The contact message was not changed."
    name = " ".join((message.name or "").split()) or "there"
    original = " ".join((message.message or "").split())
    if len(original) > 400:
        original = original[:400].rstrip() + "…"
    body = (
        f"Hello {name},\n\n"
        f"{text}\n\n"
        "You wrote:\n"
        f"{original}\n\n"
        "-- The CyberQuest Team"
    )
    try:
        send_mail(
            "Reply from CyberQuest",
            body,
            sender,
            [recipient],
            fail_silently=False,
        )
    except Exception:
        return False, "The reply could not be sent. The contact message was not changed."
    return True, ""


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


def _report_period(period):
    """7, 30, or 90 days. Anything else is all time."""
    if period not in ("7", "30", "90"):
        return "", None, None
    today = timezone.localdate()
    start = today - timedelta(days=int(period) - 1)
    start_dt = timezone.make_aware(datetime.combine(start, time.min))
    return period, start, start_dt


def _round_score(value):
    """None means no scored rows, which is different from a real zero."""
    if value is None:
        return None
    return round(value)


def _labeled_bars(bars):
    step = 1 if len(bars) <= 14 else 7
    for index, bar in enumerate(bars):
        bar["show_label"] = index % step == 0 or index == len(bars) - 1
    return bars


def _bar_series(counts, start, today):
    peak = max(counts.values(), default=0) or 1
    bars = []
    span = (today - start).days + 1
    step = 1 if span <= 14 else 7
    cursor = start
    index = 0
    while cursor <= today:
        n = counts.get(cursor, 0)
        bars.append({
            "label": cursor.strftime("%m-%d"),
            "n": n,
            "height": round(n / peak * 100) if n else 0,
            "show_label": index % step == 0 or cursor == today,
        })
        cursor += timedelta(days=1)
        index += 1
    return bars


def _day_counts(qs, field):
    counts = {}
    for row in qs.annotate(day=TruncDate(field)).values("day").annotate(n=Count("id")):
        day = row["day"].date() if hasattr(row["day"], "hour") else row["day"]
        if day is not None:
            counts[day] = row["n"]
    return counts


def analytics_report(period=""):
    """
    Read-only report. All-time rates keep the Overview course denominator.
    A selected period filters only the metrics labeled as period values.
    Student activity excludes staff and superuser accounts.
    """
    period, start, start_dt = _report_period(period)
    today = timezone.localdate()
    chart_start = start or (today - timedelta(days=89))
    chart_start_dt = timezone.make_aware(datetime.combine(chart_start, time.min))
    student_n = students().count()
    published = Course.objects.filter(is_published=True)
    published_n = published.count()
    completion_qs = CourseProgress.objects.filter(course__is_published=True, user__in=students())
    completion_n = completion_qs.count()
    possible = published_n * student_n
    completion_rate = round(completion_n / possible * 100) if possible else None

    attempts = _student_game_attempts()
    period_attempts = attempts.filter(completed_at__gte=start_dt) if start_dt else attempts
    attempt_avg = period_attempts.aggregate(v=Avg(F("score") * 100.0 / F("total_questions")))["v"]
    first_ids = attempts.values("user_id", "game_key").annotate(first_id=Min("id")).values("first_id")
    first_attempts = attempts.filter(id__in=first_ids)
    if start_dt:
        first_attempts = first_attempts.filter(completed_at__gte=start_dt)
    first_avg = first_attempts.aggregate(v=Avg(F("score") * 100.0 / F("total_questions")))["v"]

    sessions = PracticeSession.objects.filter(user__is_staff=False, user__is_superuser=False)
    period_sessions = sessions.filter(created_at__gte=start_dt) if start_dt else sessions
    completed_sessions = period_sessions.filter(status="completed", max_score__gt=0)
    practice_avg = completed_sessions.aggregate(v=Avg(F("score") * 100.0 / F("max_score")))["v"]
    session_n = period_sessions.count()
    completed_n = period_sessions.filter(status="completed").count()

    activity = UserActivityDay.objects.filter(user__is_staff=False, user__is_superuser=False)
    if start:
        activity = activity.filter(day__gte=start)
    signups = students().filter(date_joined__gte=start_dt).count() if start_dt else student_n
    ready_certs = IssuedCertificate.objects.exclude(pdf_file="").filter(
        user__is_staff=False, user__is_superuser=False,
    )
    period_certs = ready_certs.filter(issued_at__gte=start_dt).count() if start_dt else ready_certs.count()
    awards = UserBadge.objects.filter(user__is_staff=False, user__is_superuser=False)
    period_awards = awards.filter(earned_at__gte=start_dt).count() if start_dt else awards.count()

    course_rows = []
    course_qs = published.annotate(
        completed=Count(
            "progress_records",
            filter=Q(progress_records__user__is_staff=False, progress_records__user__is_superuser=False),
        ),
        readers=Count(
            "reading_progress",
            filter=Q(reading_progress__user__is_staff=False, reading_progress__user__is_superuser=False),
            distinct=True,
        ),
        period_completed=Count(
            "progress_records",
            filter=Q(
                progress_records__user__is_staff=False,
                progress_records__user__is_superuser=False,
                **({} if start_dt is None else {"progress_records__completed_at__gte": start_dt}),
            ),
        ),
    ).order_by("order", "code")
    for course in course_qs:
        course_rows.append({
            "code": course.code,
            "title": course.title,
            "completed": course.completed,
            "period_completed": course.period_completed,
            "readers": course.readers,
            "percent": round(course.completed / student_n * 100) if student_n else None,
        })
    ranked = [row for row in course_rows if row["completed"]]
    busiest = max(ranked, key=lambda row: (row["completed"], row["code"]), default=None)
    low = None
    low_note = ""
    if course_rows and student_n < 3:
        low_note = "At least 3 student accounts are needed before course rates are compared."
    elif student_n >= 3 and course_rows:
        percents = [row["percent"] for row in course_rows if row["percent"] is not None]
        if percents and min(percents) < max(percents):
            floor = min(percents)
            low = [row for row in course_rows if row["percent"] == floor]
            low_note = ""
        elif percents:
            low_note = "Published courses currently share the same completion rate."
        else:
            low_note = ""

    names = {item["key"]: item["name"] for item in GAMES_REGISTRY}
    bank_labels = dict(SET_COURSES)
    grouped = {
        row["game_key"]: row
        for row in period_attempts.values("game_key").annotate(
            attempts=Count("id"),
            students=Count("user", distinct=True),
            avg_percent=Avg(F("score") * 100.0 / F("total_questions")),
        )
    }
    first_grouped = {
        row["game_key"]: row["avg_percent"]
        for row in first_attempts.values("game_key").annotate(
            avg_percent=Avg(F("score") * 100.0 / F("total_questions")),
        )
    }
    game_rows = []
    seen = set()
    for item in GAMES_REGISTRY:
        seen.add(item["key"])
        row = grouped.get(item["key"]) or {}
        game_rows.append({
            "key": item["key"],
            "name": item["name"],
            "bank": bank_labels.get(item["key"]) or "Built-in questions",
            "attempts": row.get("attempts") or 0,
            "students": row.get("students") or 0,
            "avg_percent": _round_score(row.get("avg_percent")),
            "first_percent": _round_score(first_grouped.get(item["key"])),
        })
    for key, row in grouped.items():
        if key in seen or not key:
            continue
        game_rows.append({
            "key": key,
            "name": names.get(key, key),
            "bank": bank_labels.get(key) or "Built-in questions",
            "attempts": row["attempts"],
            "students": row["students"],
            "avg_percent": _round_score(row["avg_percent"]),
            "first_percent": _round_score(first_grouped.get(key)),
        })
    game_peak = max((row["attempts"] for row in game_rows), default=0) or 1
    for row in game_rows:
        row["height"] = round(row["attempts"] / game_peak * 100) if row["attempts"] else 0

    domain_labels = {item["slug"]: item["full_label"] for item in DOMAINS}
    practice_grouped = {
        (row["domain"], row["activity_type"]): row
        for row in period_sessions.values("domain", "activity_type").annotate(
            sessions=Count("id"),
            completed=Count("id", filter=Q(status="completed")),
            students=Count("user", distinct=True),
            avg_percent=Avg(
                F("score") * 100.0 / F("max_score"),
                filter=Q(status="completed", max_score__gt=0),
            ),
        )
    }
    domain_rows = []
    for item in DOMAINS:
        matches = [row for (domain, _), row in practice_grouped.items() if domain == item["slug"]]
        sessions_n = sum(row["sessions"] for row in matches)
        done_n = sum(row["completed"] for row in matches)
        domain_rows.append({
            "domain": item["full_label"],
            "sessions": sessions_n,
            "completed": done_n,
            "students": 0,
            "rate": round(done_n / sessions_n * 100) if sessions_n else None,
        })
    # Distinct students cannot be summed across activity types. Query once per domain set.
    domain_students = {
        row["domain"]: row["students"]
        for row in period_sessions.values("domain").annotate(students=Count("user", distinct=True))
    }
    domain_avgs = {
        row["domain"]: row["avg_percent"]
        for row in period_sessions.filter(status="completed", max_score__gt=0)
        .values("domain")
        .annotate(avg_percent=Avg(F("score") * 100.0 / F("max_score")))
    }
    for item, row in zip(DOMAINS, domain_rows):
        row["students"] = domain_students.get(item["slug"]) or 0
        row["avg_percent"] = _round_score(domain_avgs.get(item["slug"]))
    activity_labels = {"simulation": "Simulation", "incident": "Incident", "game": "Game"}
    activity_stats = {
        row["activity_type"]: row
        for row in period_sessions.values("activity_type").annotate(
            sessions=Count("id"),
            completed=Count("id", filter=Q(status="completed")),
            avg_percent=Avg(
                F("score") * 100.0 / F("max_score"),
                filter=Q(status="completed", max_score__gt=0),
            ),
        )
    }
    activity_rows = []
    for key, label in activity_labels.items():
        row = activity_stats.get(key) or {}
        sessions_n = row.get("sessions") or 0
        done_n = row.get("completed") or 0
        activity_rows.append({
            "activity": label,
            "sessions": sessions_n,
            "completed": done_n,
            "rate": round(done_n / sessions_n * 100) if sessions_n else None,
            "avg_percent": _round_score(row.get("avg_percent")),
        })
    practice_peak = max((row["completed"] for row in domain_rows), default=0) or 1
    for row in domain_rows:
        row["height"] = round(row["completed"] / practice_peak * 100) if row["completed"] else 0

    completed_in_chart = sessions.filter(status="completed", completed_at__gte=chart_start_dt)
    levels = [
        {"level": row["level"], "n": row["n"]}
        for row in students().values("level").annotate(n=Count("id")).order_by("level")
    ]
    level_peak = max((row["n"] for row in levels), default=0) or 1
    for row in levels:
        row["height"] = round(row["n"] / level_peak * 100) if row["n"] else 0
    questions = question_summary()
    return {
        "period": period or "all",
        "period_label": f"Last {period} days" if period else "All time",
        "chart_label": f"Last {period} days" if period else "Last 90 days",
        "students": student_n,
        "active_accounts": students().filter(is_active=True).count(),
        "active_in_period": activity.values("user").distinct().count(),
        "signups": signups,
        "published_courses": published_n,
        "completion_rate": completion_rate,
        "completions": completion_n,
        "completion_denominator": possible,
        "game_attempts": period_attempts.count(),
        "game_students": period_attempts.values("user").distinct().count(),
        "mean_game": _round_score(attempt_avg),
        "first_game": _round_score(first_avg),
        "practice_sessions": session_n,
        "practice_completed": completed_n,
        "practice_rate": round(completed_n / session_n * 100) if session_n else None,
        "practice_students": period_sessions.values("user").distinct().count(),
        "mean_practice": _round_score(practice_avg),
        "certificates": ready_certs.count(),
        "certificates_in_period": period_certs,
        "badge_students": awards.values("user").distinct().count(),
        "badges_in_period": period_awards,
        "courses": course_rows,
        "busiest_course": busiest,
        "low_courses": low,
        "low_note": low_note,
        "games": game_rows,
        "domains": domain_rows,
        "activities": activity_rows,
        "signups_chart": _labeled_bars(signup_bars(int(period) if period else 90)),
        "practice_chart": _bar_series(_day_counts(completed_in_chart, "completed_at"), chart_start, today),
        "levels": levels,
        "review_sets": questions["sets_review"],
        "review_banks": questions["review"],
        "incomplete_certificates": IssuedCertificate.objects.filter(pdf_file="").count(),
        "unread_notifications": notification_summary()["unread"],
        "open_contact": contact_summary()["open"],
        "readers": ReadingProgress.objects.filter(
            course__is_published=True, user__in=students(),
        ).values("user").distinct().count(),
    }


def manage_course_rows(query="", status=""):
    """All courses for the client course screen, including drafts."""
    qs = Course.objects.all().annotate(
        readers=Count(
            "reading_progress",
            filter=Q(reading_progress__user__is_staff=False, reading_progress__user__is_superuser=False),
            distinct=True,
        )
    )
    if query:
        qs = qs.filter(
            Q(title__icontains=query)
            | Q(code__icontains=query)
            | Q(short_description__icontains=query)
        )
    if status == "published":
        qs = qs.filter(is_published=True)
    elif status == "draft":
        qs = qs.filter(is_published=False)
    done_rows = (
        CourseProgress.objects.filter(course__in=qs, user__in=students())
        .values("course_id")
        .annotate(done=Count("id"))
    )
    by_id = {row["course_id"]: row["done"] for row in done_rows}
    student_n = students().count()
    rows = []
    for course in qs.order_by("order", "code"):
        done = by_id.get(course.id, 0)
        if course.uses_pdf():
            material = "PDF"
        elif (course.content or "").strip():
            material = "Text"
        else:
            material = "None yet"
        rows.append({
            "course": course,
            "completed": done,
            "readers": course.readers,
            "percent": round(done / student_n * 100) if student_n else 0,
            "material": material,
        })
    return rows


def course_summary():
    all_courses = Course.objects.all()
    return {
        "total": all_courses.count(),
        "published": all_courses.filter(is_published=True).count(),
        "drafts": all_courses.filter(is_published=False).count(),
        "completions": CourseProgress.objects.filter(user__in=students()).count(),
    }


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


_PLAY_DIFFICULTY = {
    "mixed": "Mixed",
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
}


def _student_game_attempts():
    """Finished student plays. Staff and superuser activity is left out."""
    return GameAttempt.objects.filter(
        user__is_staff=False,
        user__is_superuser=False,
        total_questions__gt=0,
    )


def game_usage(key):
    attempts = _student_game_attempts().filter(game_key=key)
    summary = attempts.aggregate(
        attempts=Count("id"),
        students=Count("user", distinct=True),
        avg_percent=Avg(F("score") * 100.0 / F("total_questions")),
        avg_score=Avg("score"),
        xp=Sum("xp_awarded"),
        latest=Max("completed_at"),
    )
    # The first saved attempt is the play that can award XP. Later rows are replays.
    first_ids = attempts.values("user").annotate(first_id=Min("id")).values("first_id")
    first = attempts.filter(id__in=first_ids).aggregate(
        avg_percent=Avg(F("score") * 100.0 / F("total_questions")),
    )
    attempt_count = summary["attempts"] or 0
    students = summary["students"] or 0
    return {
        "attempts": attempt_count,
        "completed": attempt_count,
        "students": students,
        "replays": max(attempt_count - students, 0),
        "avg_percent": round(summary["avg_percent"] or 0),
        "avg_score": round(summary["avg_score"] or 0),
        "first_avg_percent": round(first["avg_percent"] or 0),
        "xp": summary["xp"] or 0,
        "latest": summary["latest"],
    }


def game_catalog(query="", game="", bank_id=None):
    """Read-only list of the built-in games. Does not create or change game definitions."""
    labels = {item["key"]: item for item in GAMES_REGISTRY}
    course_labels = dict(SET_COURSES)
    allowed = set(labels)
    if game not in allowed:
        game = ""
    bank = None
    if bank_id:
        bank = QuestionBank.objects.filter(pk=bank_id, domain__in=allowed).first()
        if bank is not None:
            if game and game != bank.domain:
                return []
            game = bank.domain
    needle = (query or "").strip().lower()
    stored = {
        row["course"]: row["n"]
        for row in (
            Question.objects.filter(is_active=True, course__in=SET_COURSE_KEYS)
            .values("course")
            .annotate(n=Count("id"))
        )
    }
    rows = []
    for item in GAMES_REGISTRY:
        if game and item["key"] != game:
            continue
        key = item["key"]
        bank_label = course_labels.get(key, "")
        haystack = " ".join([
            item["name"],
            item.get("description") or "",
            key,
            bank_label,
        ]).lower()
        if needle and needle not in haystack:
            continue
        config = GAME_QUESTION_CONFIG.get(key)
        builtin = QUIZ_GAMES.get(key) or {}
        builtin_count = len(builtin.get("questions") or [])
        has_bank = key in SET_COURSE_KEYS
        usable = approved_question_pool(key).count() if has_bank else 0
        current = latest_approved_bank(key) if has_bank else None
        rows.append({
            "key": key,
            "name": item["name"],
            "description": item.get("description") or "",
            "has_bank": has_bank,
            "bank_label": bank_label,
            "question_count": stored.get(key, 0) if has_bank else builtin_count,
            "usable_questions": usable,
            "builtin_questions": builtin_count,
            "attempt_size": config.get("attempt_size") if config else builtin_count,
            "bank_id": current.pk if current else None,
            "bank_title": current.title if current else "",
            "usage": game_usage(key),
        })
    return rows


def game_detail(key):
    item = next((row for row in GAMES_REGISTRY if row["key"] == key), None)
    if item is None:
        return None
    row = game_catalog(game=key)
    detail = dict(row[0]) if row else None
    if detail is None:
        return None
    if key in SET_COURSE_KEYS:
        detail["banks"] = list(
            QuestionBank.objects.filter(domain=key).order_by("-created_at", "-id")
        )
    else:
        detail["banks"] = []
    config = GAME_QUESTION_CONFIG.get(key) or {}
    detail["questions_per_play"] = config.get("attempt_size") or detail["builtin_questions"]
    detail["default_mcq"] = config.get("default_mcq")
    detail["default_simulation"] = config.get("default_simulation")
    detail["default_difficulty"] = _PLAY_DIFFICULTY.get(
        config.get("difficulty_mode"), config.get("difficulty_mode") or ""
    )
    detail["includes_simulations"] = "simulation" in (config.get("allowed_types") or ())
    detail["xp_per_correct"] = XP_PER_CORRECT_ANSWER
    detail["live_play"] = None
    if detail["bank_id"] and key in GAME_QUESTION_CONFIG:
        approved = QuestionBank.objects.filter(pk=detail["bank_id"]).first()
        if approved is not None:
            cfg = resolve_attempt_config(key, approved)
            mode = cfg.get("difficulty_mode") or ""
            detail["live_play"] = {
                "title": approved.title,
                "questions": cfg["attempt_size"],
                "mcq": cfg["mcq_count"],
                "simulation": cfg["simulation_count"],
                "difficulty": _PLAY_DIFFICULTY.get(mode, mode),
            }
    return detail


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


_ACTIVITY_LABELS = {"simulation": "Simulation", "incident": "Incident"}
_DIFFICULTY_LABELS = {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
}
_QUALITY_LABELS = {"correct": "Recommended", "unsafe": "Unsafe", "poor": "Weak"}
_WORKSPACE_LABELS = {
    "email": "Email",
    "auth": "Sign-in",
    "network": "Network",
    "crypto": "Cryptography",
    "osint": "Open sources",
}


def _scenario_usage():
    rows = (
        PracticeSession.objects.filter(user__is_staff=False, user__is_superuser=False)
        .values("scenario_key")
        .annotate(
            sessions=Count("id"),
            completed=Count("id", filter=Q(status="completed")),
            students=Count("user", distinct=True),
            avg_score=Avg("score", filter=Q(status="completed")),
            latest=Max("created_at"),
        )
    )
    return {row["scenario_key"]: row for row in rows}


def _usage_for(key, usage):
    row = usage.get(key) or {}
    return {
        "sessions": row.get("sessions") or 0,
        "completed": row.get("completed") or 0,
        "students": row.get("students") or 0,
        "avg_score": round(row.get("avg_score") or 0),
        "latest": row.get("latest"),
    }


def practice_scenario_rows(query="", domain="", activity="", difficulty=""):
    """Read-only catalog. Does not copy or change the scenario definitions."""
    usage = _scenario_usage()
    labels = {item["slug"]: item["full_label"] for item in DOMAINS}
    needle = (query or "").strip().lower()
    rows = []
    for scenario in SCENARIOS.values():
        if domain and scenario.get("domain") != domain:
            continue
        if activity and scenario.get("activity_type") != activity:
            continue
        if difficulty and scenario.get("difficulty") != difficulty:
            continue
        briefing = scenario.get("briefing") or {}
        title = scenario.get("title") or scenario.get("key")
        objective = scenario.get("objective") or ""
        summary = briefing.get("summary") or ""
        haystack = " ".join([title, objective, summary, scenario.get("incident_code") or ""]).lower()
        if needle and needle not in haystack:
            continue
        rows.append({
            "key": scenario["key"],
            "title": title,
            "domain": scenario.get("domain") or "",
            "domain_label": labels.get(scenario.get("domain"), scenario.get("domain") or ""),
            "activity": scenario.get("activity_type") or "",
            "activity_label": _ACTIVITY_LABELS.get(scenario.get("activity_type"), "Practice"),
            "difficulty": scenario.get("difficulty") or "",
            "difficulty_label": _DIFFICULTY_LABELS.get(scenario.get("difficulty"), "Not set"),
            "summary": summary,
            "usage": _usage_for(scenario["key"], usage),
        })
    rows.sort(key=lambda row: (row["domain_label"], row["title"]))
    return rows


def practice_scenario_view(key):
    scenario = get_scenario(key)
    if not scenario:
        return None
    labels = {item["slug"]: item["full_label"] for item in DOMAINS}
    investigations = scenario.get("investigations") or {}
    required = set(scenario.get("required_evidence") or [])
    checks = []
    for action_key, action in investigations.items():
        reveal = action.get("reveal") or {}
        checks.append({
            "label": action.get("label") or action_key,
            "required": action_key in required,
            "finding": reveal.get("title") or "",
            "details": list(reveal.get("fields") or []),
            "note": reveal.get("feedback") or "",
        })
    decisions = []
    for action in (scenario.get("decisions") or {}).values():
        decisions.append({
            "label": action.get("label") or "",
            "quality": _QUALITY_LABELS.get(action.get("quality"), "Decision"),
            "score": action.get("score"),
            "result_title": action.get("consequence_title") or "",
            "result": action.get("consequence") or "",
        })
    scene = scenario.get("scene") or {}
    suspicious = set(scene.get("suspicious") or [])
    nodes = [
        {"label": node.get("label") or node.get("id"), "suspicious": node.get("id") in suspicious}
        for node in (scene.get("nodes") or [])
    ]
    briefing = scenario.get("briefing") or {}
    workspace = scenario.get("workspace") or {}
    return {
        "key": scenario["key"],
        "title": scenario.get("title") or scenario["key"],
        "domain_label": labels.get(scenario.get("domain"), scenario.get("domain") or ""),
        "activity_label": _ACTIVITY_LABELS.get(scenario.get("activity_type"), "Practice"),
        "difficulty_label": _DIFFICULTY_LABELS.get(scenario.get("difficulty"), "Not set"),
        "objective": scenario.get("objective") or "",
        "summary": briefing.get("summary") or "",
        "employee": briefing.get("employee") or "",
        "department": briefing.get("department") or "",
        "subject": briefing.get("subject") or workspace.get("subject") or "",
        "environment": scenario.get("environment") or "",
        "workspace_label": _WORKSPACE_LABELS.get(scenario.get("workspace_type"), ""),
        "incident_code": scenario.get("incident_code") or "",
        "severity": scenario.get("severity") or "",
        "checks": checks,
        "decisions": decisions,
        "nodes": nodes,
        "usage": _usage_for(scenario["key"], _scenario_usage()),
    }


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


def question_reaches_students(question):
    """True when this question can be served by an approved, active set."""
    if not question.is_active:
        return False
    playable = question.sets.filter(is_active=True, status=QuestionSet.STATUS_APPROVED)
    return playable.filter(
        Q(question_bank__isnull=True) | Q(question_bank__status=QuestionBank.STATUS_APPROVED)
    ).exists()


def question_bank_list(query="", status="", domain=""):
    qs = QuestionBank.objects.all().annotate(
        question_count=Count("question_sets__questions", distinct=True),
        review_sets=Count(
            "question_sets",
            filter=Q(question_sets__status=QuestionSet.STATUS_REVIEW),
            distinct=True,
        ),
        approved_sets=Count(
            "question_sets",
            filter=Q(question_sets__status=QuestionSet.STATUS_APPROVED),
            distinct=True,
        ),
    )
    if query:
        qs = qs.filter(Q(title__icontains=query) | Q(description__icontains=query))
    if status:
        qs = qs.filter(status=status)
    if domain:
        qs = qs.filter(domain=domain)
    return qs.order_by("-created_at")


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


_HEALTH_LABELS = {
    "healthy": ("Healthy", "ops-s-good"),
    "warning": ("Warning", "ops-s-warn"),
    "attention": ("Needs attention", "ops-s-bad"),
    "unknown": ("Unknown", ""),
}


def _health_item(name, status, detail, kind):
    label, badge = _HEALTH_LABELS[status]
    return {
        "name": name,
        "status": status,
        "label": label,
        "badge": badge,
        "detail": _redact(detail),
        "kind": kind,
    }


def _redact(text):
    """Remove known secret values from a status sentence. Never log the original."""
    cleaned = text or ""
    for value in (
        getattr(settings, "SECRET_KEY", ""),
        getattr(settings, "EMAIL_HOST_PASSWORD", "") or "",
        getattr(settings, "EMAIL_HOST_USER", "") or "",
        getattr(settings, "GOOGLE_CLIENT_SECRET", "") or "",
        getattr(settings, "GOOGLE_CLIENT_ID", "") or "",
        getattr(settings, "GEMINI_API_KEY", "") or "",
        os.environ.get("DATABASE_URL", "") or "",
        os.environ.get("DEFAULT_FROM_EMAIL_ADDRESS", "") or "",
    ):
        if value and len(value) >= 8:
            cleaned = cleaned.replace(value, "[redacted]")
    return cleaned


def _env_set(name):
    return bool((os.environ.get(name) or "").strip())


def _database_reachable():
    connection.ensure_connection()


def _backend_name(engine):
    engine = engine or ""
    if "sqlite" in engine:
        return "SQLite"
    if "postgres" in engine:
        return "PostgreSQL"
    if "mysql" in engine:
        return "MySQL"
    return "Other"


def system_health():
    """
    Read-only status report. Configuration rows describe Django settings.
    Live rows are connectivity or files on disk. Nothing here is changed.
    """
    debug = bool(settings.DEBUG)
    groups = []

    environment = []
    if debug:
        environment.append(_health_item(
            "Environment", "warning",
            "Debug is on, so this process is running as development.",
            "Configuration",
        ))
        environment.append(_health_item(
            "Debug mode", "warning", "On.", "Configuration",
        ))
    else:
        environment.append(_health_item(
            "Environment", "healthy",
            "Debug is off. This is the production flag, not a live check of the host.",
            "Configuration",
        ))
        environment.append(_health_item(
            "Debug mode", "healthy", "Off.", "Configuration",
        ))
    secret = (os.environ.get("SECRET_KEY") or "").strip()
    if not secret:
        environment.append(_health_item(
            "Secret key",
            "warning" if debug else "attention",
            "SECRET_KEY is not set in the environment.",
            "Configuration",
        ))
    elif secret.startswith("django-insecure"):
        environment.append(_health_item(
            "Secret key",
            "warning" if debug else "attention",
            "SECRET_KEY is set, and it uses Django's local insecure prefix.",
            "Configuration",
        ))
    else:
        environment.append(_health_item(
            "Secret key", "healthy", "SECRET_KEY is set.", "Configuration",
        ))
    environment.append(_health_item(
        "Application version", "unknown",
        "No application version or build identifier is defined.",
        "Configuration",
    ))
    import django
    environment.append(_health_item(
        "Django version", "healthy", f"Django {django.get_version()} is installed.", "Configuration",
    ))
    groups.append({"title": "Environment", "items": environment})

    engine = settings.DATABASES.get("default", {}).get("ENGINE", "")
    database = [_health_item(
        "Database backend", "healthy",
        f"{_backend_name(engine)} is configured.",
        "Configuration",
    )]
    if not _env_set("DATABASE_URL"):
        database.append(_health_item(
            "Database URL",
            "warning" if debug else "attention",
            "DATABASE_URL is not set. Local SQLite is the project default.",
            "Configuration",
        ))
    else:
        database.append(_health_item(
            "Database URL", "healthy", "DATABASE_URL is set.", "Configuration",
        ))
    try:
        _database_reachable()
        database.append(_health_item(
            "Database connectivity", "healthy", "A connection was opened.", "Live check",
        ))
        db_up = True
    except Exception:
        database.append(_health_item(
            "Database connectivity", "attention",
            "A connection could not be opened.",
            "Live check",
        ))
        db_up = False
    if not db_up:
        database.append(_health_item(
            "Pending migrations", "unknown",
            "Not checked because the database connection failed. Migrations were not run.",
            "Live check",
        ))
    else:
        try:
            from django.db.migrations.executor import MigrationExecutor
            executor = MigrationExecutor(connection)
            pending = len(executor.migration_plan(executor.loader.graph.leaf_nodes()))
            if pending:
                database.append(_health_item(
                    "Pending migrations", "warning",
                    f"{pending} migrations are not applied. They were not run from this page.",
                    "Live check",
                ))
            else:
                database.append(_health_item(
                    "Pending migrations", "healthy",
                    "No migrations are pending. None were run from this page.",
                    "Live check",
                ))
        except Exception:
            database.append(_health_item(
                "Pending migrations", "unknown",
                "The migration list could not be read. Migrations were not run.",
                "Live check",
            ))
    groups.append({"title": "Database", "items": database})

    static_backend = (
        settings.STORAGES.get("staticfiles", {}).get("BACKEND", "")
    ).rsplit(".", 1)[-1] or "Not set"
    files = [_health_item(
        "Static files",
        "healthy" if settings.STATIC_URL and settings.STATIC_ROOT else "attention",
        f"Static URL is configured. Storage is {static_backend}.",
        "Configuration",
    )]
    if debug:
        files.append(_health_item(
            "Collected static files", "unknown",
            "Not required while Debug is on, so this was not treated as healthy or failed.",
            "Live check",
        ))
    else:
        root = Path(settings.STATIC_ROOT)
        try:
            present = root.is_dir() and any(root.iterdir())
        except OSError:
            present = False
        files.append(_health_item(
            "Collected static files",
            "healthy" if present else "attention",
            "Collected static files are present." if present else "Collected static files were not found.",
            "Live check",
        ))
    media_configured = bool(settings.MEDIA_URL and settings.MEDIA_ROOT)
    files.append(_health_item(
        "Media configuration",
        "healthy" if media_configured else "attention",
        "Media URL and storage location are configured." if media_configured else "Media settings are incomplete.",
        "Configuration",
    ))
    try:
        media_ready = Path(settings.MEDIA_ROOT).is_dir()
    except OSError:
        media_ready = False
    files.append(_health_item(
        "Media directory",
        "healthy" if media_ready else "warning",
        "The media directory is present." if media_ready else "The media directory is not present.",
        "Live check",
    ))
    groups.append({"title": "Files", "items": files})

    email_backend = (settings.EMAIL_BACKEND or "").rsplit(".", 1)[-1]
    smtp = "smtp" in (settings.EMAIL_BACKEND or "").lower()
    email = [_health_item(
        "Email backend", "healthy" if settings.EMAIL_BACKEND else "attention",
        "SMTP is selected." if smtp else f"{email_backend or 'Not set'} is selected.",
        "Configuration",
    )]
    credentials = all([
        (settings.EMAIL_HOST_USER or "").strip(),
        (settings.EMAIL_HOST_PASSWORD or "").strip(),
        (settings.DEFAULT_FROM_EMAIL or "").strip(),
    ])
    if smtp and credentials:
        email.append(_health_item(
            "Email credentials", "warning",
            "The SMTP username, password, and from address are set. Delivery was not tested.",
            "Configuration",
        ))
    elif smtp:
        email.append(_health_item(
            "Email credentials", "attention",
            "SMTP is selected, and the username, password, or from address is missing.",
            "Configuration",
        ))
    else:
        email.append(_health_item(
            "Email credentials", "unknown",
            "This backend does not use the SMTP username and password settings.",
            "Configuration",
        ))
    email.append(_health_item(
        "Email delivery", "unknown",
        "No test message was sent, so delivery cannot be confirmed.",
        "Live check",
    ))
    groups.append({"title": "Email", "items": email})

    security = []
    csrf_on = "django.middleware.csrf.CsrfViewMiddleware" in settings.MIDDLEWARE
    security.append(_health_item(
        "CSRF middleware",
        "healthy" if csrf_on else "attention",
        "CSRF middleware is enabled." if csrf_on else "CSRF middleware is not enabled.",
        "Configuration",
    ))
    origins = len(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or [])
    if origins:
        security.append(_health_item(
            "CSRF trusted origins", "healthy",
            f"{origins} trusted origins are configured.",
            "Configuration",
        ))
    else:
        security.append(_health_item(
            "CSRF trusted origins",
            "warning",
            "No extra trusted origins are configured.",
            "Configuration",
        ))
    https_on = bool(getattr(settings, "SECURE_SSL_REDIRECT", False))
    cookies_on = bool(getattr(settings, "SESSION_COOKIE_SECURE", False)) and bool(
        getattr(settings, "CSRF_COOKIE_SECURE", False)
    )
    hsts_seconds = int(getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0)
    if debug:
        security.append(_health_item(
            "HTTPS redirect",
            "healthy" if https_on else "warning",
            "On." if https_on else "Off while Debug is on.",
            "Configuration",
        ))
        security.append(_health_item(
            "Secure cookies",
            "healthy" if cookies_on else "warning",
            "Session and CSRF cookies are marked secure." if cookies_on else "Off while Debug is on.",
            "Configuration",
        ))
        security.append(_health_item(
            "HSTS",
            "healthy" if hsts_seconds else "warning",
            "Enabled." if hsts_seconds else "Off while Debug is on.",
            "Configuration",
        ))
    else:
        security.append(_health_item(
            "HTTPS redirect",
            "healthy" if https_on else "attention",
            "On." if https_on else "Off while Debug is off.",
            "Configuration",
        ))
        security.append(_health_item(
            "Secure cookies",
            "healthy" if cookies_on else "attention",
            "Session and CSRF cookies are marked secure." if cookies_on else "Session or CSRF cookies are not marked secure.",
            "Configuration",
        ))
        security.append(_health_item(
            "HSTS",
            "healthy" if hsts_seconds else "attention",
            "Enabled." if hsts_seconds else "Off while Debug is off.",
            "Configuration",
        ))
    import cyberquest.settings as project_settings
    if "LOGGING" in vars(project_settings):
        security.append(_health_item(
            "Logging", "healthy", "A logging configuration is defined.", "Configuration",
        ))
    else:
        security.append(_health_item(
            "Logging", "unknown",
            "The project settings do not define logging. Django's built-in default is in use.",
            "Configuration",
        ))
    groups.append({"title": "Security", "items": security})

    google_id = bool((settings.GOOGLE_CLIENT_ID or "").strip())
    google_secret = bool((settings.GOOGLE_CLIENT_SECRET or "").strip())
    if google_id and google_secret:
        google_status, google_detail = "warning", "Google sign-in credentials are set. No sign-in was attempted."
    elif google_id or google_secret:
        google_status, google_detail = "attention", "Google sign-in is only partly configured."
    else:
        google_status, google_detail = "warning", "Google sign-in credentials are not set."
    gemini = bool((settings.GEMINI_API_KEY or "").strip())
    public_url = bool((settings.PUBLIC_BASE_URL or "").strip())
    groups.append({
        "title": "Integrations",
        "items": [
            _health_item("Google sign-in", google_status, google_detail, "Configuration"),
            _health_item(
                "Gemini API key",
                "warning",
                "Set. No request was sent to the provider." if gemini else "Optional AI key is not set.",
                "Configuration",
            ),
            _health_item(
                "Public site URL",
                "healthy" if public_url else "warning",
                "Set." if public_url else "Not set. Certificate links can fall back to the request host.",
                "Configuration",
            ),
        ],
    })

    findings = []
    deploy_status = "healthy"
    deploy_detail = "Deployment checks reported no warnings."
    try:
        from django.core import checks as django_checks
        issues = django_checks.run_checks(include_deployment_checks=True)
        interesting = [
            issue for issue in issues
            if issue.id.startswith("security.") or issue.level >= 40
        ]
        if any(issue.level >= 40 for issue in interesting):
            deploy_status = "attention"
            deploy_detail = "Deployment checks reported an error."
        elif interesting:
            deploy_status = "warning"
            deploy_detail = "Deployment checks reported warnings."
        for issue in interesting[:8]:
            findings.append(_redact(f"{issue.id}: {issue.msg}"))
    except Exception:
        deploy_status = "unknown"
        deploy_detail = "Deployment checks could not be completed."
    groups.append({
        "title": "Deployment checks",
        "items": [_health_item("Django deployment checks", deploy_status, deploy_detail, "Configuration")],
        "findings": findings,
    })
    return groups
