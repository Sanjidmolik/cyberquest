from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from achievements.models import Badge, UserBadge
from certificates.eligibility import is_eligible_for_certificate
from certificates.models import IssuedCertificate
from courses.models import CourseProgress, ReadingProgress
from games.models import GameAttempt, QuestionSet
from notifications.models import Notification
from notifications.utils import notify
from pages.models import ContactMessage
from practice.models import PracticeSession
from question_bank.models import QuestionBank

from .ops import (
    course_rows,
    game_rows,
    overview_kpis,
    practice_rows,
    question_summary,
    recent_activity,
    signup_bars,
    students as student_qs,
)
from .ops_access import superuser_required

from django.contrib.auth import get_user_model

User = get_user_model()


def _page(request, qs, per=20):
    return Paginator(qs, per).get_page(request.GET.get("page") or 1)


def _shell(request, active, title, **extra):
    extra.update({
        "active": active,
        "page_title": title,
        "open_contact": ContactMessage.objects.filter(is_resolved=False).count(),
    })
    return extra


@superuser_required
def overview(request):
    ctx = _shell(request, "overview", "Overview")
    ctx.update({
        "kpis": overview_kpis(),
        "activity": recent_activity(),
        "signups": signup_bars(),
    })
    return render(request, "dashboard/ops/overview.html", ctx)


@superuser_required
def students(request):
    qs = student_qs().annotate(
        course_done=Count("course_progress", distinct=True),
        attempts=Count("game_attempts", distinct=True),
        practices=Count("practice_sessions", distinct=True),
    )
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(username__icontains=q) | Q(full_name__icontains=q))
    status = request.GET.get("status", "")
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    qs = qs.order_by("-date_joined")
    ctx = _shell(request, "students", "Students")
    ctx.update({"page_obj": _page(request, qs), "q": q, "status": status})
    return render(request, "dashboard/ops/students.html", ctx)


@superuser_required
def student_detail(request, pk):
    user = get_object_or_404(student_qs(), pk=pk)
    courses = CourseProgress.objects.filter(user=user).select_related("course")
    attempts = (
        GameAttempt.objects.filter(user=user)
        .values("game_key")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    ctx = _shell(request, "students", user.display_name())
    ctx.update({
        "learner": user,
        "courses": courses,
        "reading": ReadingProgress.objects.filter(user=user).count(),
        "attempts": attempts,
        "practices": PracticeSession.objects.filter(user=user).order_by("-created_at")[:12],
        "badges": UserBadge.objects.filter(user=user).select_related("badge"),
        "certificate": IssuedCertificate.objects.filter(user=user).first(),
        "eligible": is_eligible_for_certificate(user),
    })
    return render(request, "dashboard/ops/student.html", ctx)


@superuser_required
def courses(request):
    ctx = _shell(request, "courses", "Courses")
    ctx["rows"] = course_rows()
    return render(request, "dashboard/ops/courses.html", ctx)


@superuser_required
def games(request):
    ctx = _shell(request, "games", "Games")
    ctx["rows"] = game_rows()
    return render(request, "dashboard/ops/games.html", ctx)


@superuser_required
def practice(request):
    ctx = _shell(request, "practice", "Practice")
    ctx["rows"] = practice_rows()
    ctx["recent"] = PracticeSession.objects.select_related("user").order_by("-created_at")[:15]
    return render(request, "dashboard/ops/practice.html", ctx)


@superuser_required
def questions(request):
    qs = QuestionBank.objects.all()
    status = request.GET.get("status", "")
    if status:
        qs = qs.filter(status=status)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(title__icontains=q)
    ctx = _shell(request, "questions", "Question bank")
    ctx.update({
        "summary": question_summary(),
        "page_obj": _page(request, qs.order_by("-created_at")),
        "status": status,
        "q": q,
        "statuses": QuestionBank.STATUS_CHOICES,
    })
    return render(request, "dashboard/ops/questions.html", ctx)


@superuser_required
def review(request):
    banks = (
        QuestionBank.objects.filter(status=QuestionBank.STATUS_REVIEW)
        .prefetch_related("question_sets__questions")
        .order_by("-updated_at")
    )
    ctx = _shell(request, "review", "AI review")
    ctx["banks"] = banks[:30]
    return render(request, "dashboard/ops/review.html", ctx)


@superuser_required
@require_POST
def approve_bank(request, pk):
    bank = get_object_or_404(QuestionBank, pk=pk)
    if bank.status not in {QuestionBank.STATUS_REVIEW, QuestionBank.STATUS_APPROVED}:
        messages.error(request, "Only banks that are ready for review can be approved.")
        return redirect("ops:review")
    bank.status = QuestionBank.STATUS_APPROVED
    bank.save(update_fields=["status", "updated_at"])
    updated = QuestionSet.objects.filter(
        question_bank=bank, status=QuestionSet.STATUS_REVIEW
    ).update(status=QuestionSet.STATUS_APPROVED)
    messages.success(request, f"Approved {bank.title} ({updated} sets).")
    return redirect("ops:review")


@superuser_required
@require_POST
def reject_set(request, pk):
    qset = get_object_or_404(QuestionSet, pk=pk)
    if qset.status != QuestionSet.STATUS_REVIEW:
        messages.error(request, "Only sets waiting for review can be rejected.")
        return redirect("ops:review")
    qset.status = QuestionSet.STATUS_REJECTED
    qset.save(update_fields=["status", "updated_at"])
    messages.success(request, f"Rejected set {qset.set_number}.")
    return redirect("ops:review")


@superuser_required
def certificates(request):
    qs = IssuedCertificate.objects.select_related("user").order_by("-issued_at")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(certificate_id__icontains=q) | Q(recipient_name__icontains=q) | Q(user__email__icontains=q))
    ctx = _shell(request, "certificates", "Certificates")
    ctx.update({"page_obj": _page(request, qs), "q": q, "issued_total": IssuedCertificate.objects.count()})
    return render(request, "dashboard/ops/certificates.html", ctx)


@superuser_required
def achievements(request):
    badges = Badge.objects.annotate(earned=Count("awarded_to")).order_by("name")
    ctx = _shell(request, "achievements", "Achievements")
    ctx["badges"] = badges
    ctx["recent"] = UserBadge.objects.select_related("user", "badge").order_by("-earned_at")[:20]
    return render(request, "dashboard/ops/achievements.html", ctx)


@superuser_required
def leaderboard(request):
    qs = student_qs().filter(is_active=True).exclude(username__isnull=True).exclude(username="").order_by("-xp", "id")
    ctx = _shell(request, "leaderboard", "Leaderboard")
    ctx["page_obj"] = _page(request, qs, per=25)
    return render(request, "dashboard/ops/leaderboard.html", ctx)


@superuser_required
def notifications(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        message = request.POST.get("message", "").strip()[:255]
        link = request.POST.get("link_url", "").strip()
        user = User.objects.filter(email__iexact=email).first()
        if not user or not message:
            messages.error(request, "A known student email and a message are required.")
        elif link and not url_has_allowed_host_and_scheme(
            url=link, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            messages.error(request, "Notification links must stay on this site.")
        else:
            notify(user, message, link)
            messages.success(request, f"Notification sent to {user.email}.")
        return redirect("ops:notifications")
    ctx = _shell(request, "notifications", "Notifications")
    ctx["page_obj"] = _page(request, Notification.objects.select_related("user"))
    ctx["unread"] = Notification.objects.filter(is_read=False).count()
    return render(request, "dashboard/ops/notifications.html", ctx)


@superuser_required
def contact(request):
    qs = ContactMessage.objects.all()
    state = request.GET.get("state", "")
    if state == "open":
        qs = qs.filter(is_resolved=False)
    elif state == "resolved":
        qs = qs.filter(is_resolved=True)
    ctx = _shell(request, "contact", "Contact")
    ctx.update({"page_obj": _page(request, qs), "state": state})
    return render(request, "dashboard/ops/contact.html", ctx)


@superuser_required
@require_POST
def resolve_contact(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    msg.is_resolved = request.POST.get("resolved") == "1"
    msg.save(update_fields=["is_resolved"])
    return redirect("ops:contact")


@superuser_required
def search(request):
    q = request.GET.get("q", "").strip()
    ctx = _shell(request, "search", "Search")
    ctx["q"] = q
    if q:
        ctx["people"] = student_qs().filter(
            Q(email__icontains=q) | Q(username__icontains=q) | Q(full_name__icontains=q)
        )[:12]
        ctx["course_hits"] = course_rows()
        ctx["course_hits"] = [row for row in ctx["course_hits"] if q.lower() in row["course"].title.lower() or q.lower() in row["course"].code.lower()][:12]
        ctx["banks"] = QuestionBank.objects.filter(title__icontains=q)[:12]
        ctx["certs"] = IssuedCertificate.objects.filter(
            Q(certificate_id__icontains=q) | Q(recipient_name__icontains=q)
        ).select_related("user")[:12]
        ctx["contact_hits"] = ContactMessage.objects.filter(
            Q(name__icontains=q) | Q(email__icontains=q) | Q(message__icontains=q)
        )[:12]
    return render(request, "dashboard/ops/search.html", ctx)


@superuser_required
def analytics(request):
    ctx = _shell(request, "analytics", "Analytics")
    ctx["signups"] = signup_bars(30)
    ctx["games"] = game_rows()
    ctx["practice"] = practice_rows()
    return render(request, "dashboard/ops/analytics.html", ctx)


@superuser_required
def settings_page(request):
    pending = None
    db_ok = True
    try:
        connection.ensure_connection()
    except Exception:
        db_ok = False
    try:
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        pending = len(executor.migration_plan(executor.loader.graph.leaf_nodes()))
    except Exception:
        pending = None
    ctx = _shell(request, "settings", "Settings")
    ctx.update({
        "debug": settings.DEBUG,
        "db_ok": db_ok,
        "pending_migrations": pending,
    })
    return render(request, "dashboard/ops/settings.html", ctx)
