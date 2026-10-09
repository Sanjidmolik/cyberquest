from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from achievements.models import Badge
from certificates.models import IssuedCertificate
from courses.models import Course, CourseProgress, ReadingProgress
from courses.progress import server_total_pages
from games.models import SET_COURSES, GameAttempt, Question, QuestionSet
from games.registry import GAMES_REGISTRY
from notifications.models import Notification
from notifications.views import _safe_notification_target
from accounts.emails import send_account_status_email
from pages.models import ContactMessage
from practice.models import PracticeSession
from practice.scenarios import DOMAINS
from question_bank.models import QuestionBank

from .ops import (
    course_rows,
    course_summary,
    game_catalog,
    game_detail,
    game_rows,
    manage_course_rows,
    set_student_active,
    student_directory,
    student_levels,
    student_profile,
    student_summary,
    overview_kpis,
    question_bank_list,
    question_reaches_students,
    practice_rows,
    practice_scenario_rows,
    practice_scenario_view,
    achievement_directory,
    achievement_earners,
    achievement_summary,
    leaderboard_directory,
    leaderboard_summary,
    analytics_report,
    contact_directory,
    contact_summary,
    create_command_superuser,
    notification_directory,
    notification_summary,
    send_student_notification,
    send_contact_reply,
    set_contact_resolved,
    certificate_detail_context,
    certificate_directory,
    certificate_summary,
    eligible_students_without_certificate,
    question_summary,
    recent_activity,
    system_health,
    signup_bars,
    students as student_qs,
)
from .ops_access import superuser_required
from .ops_forms import CourseManageForm, QuestionTextForm

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
@require_http_methods(["GET", "HEAD"])
def students(request):
    status = request.GET.get("status", "")
    if status not in ("", "active", "inactive"):
        status = ""
    activity = request.GET.get("activity", "")
    if activity not in ("", "recent", "never"):
        activity = ""
    level = request.GET.get("level", "").strip()
    if not level.isdigit():
        level = ""
    q = request.GET.get("q", "").strip()
    page = _page(request, student_directory(q, status, level, activity))
    published = Course.objects.filter(is_published=True).count()
    for learner in page.object_list:
        learner.progress_percent = round(learner.course_done / published * 100) if published else 0
    ctx = _shell(request, "students", "Students")
    ctx.update({
        "page_obj": page,
        "summary": student_summary(),
        "levels": student_levels(),
        "published": published,
        "q": q,
        "status": status,
        "level": level,
        "activity": activity,
    })
    return render(request, "dashboard/ops/students.html", ctx)


@superuser_required
@require_http_methods(["GET", "HEAD"])
def student_detail(request, pk):
    user = get_object_or_404(student_qs(), pk=pk)
    ctx = _shell(request, "students", user.display_name())
    ctx["profile"] = student_profile(user)
    return render(request, "dashboard/ops/student.html", ctx)


@superuser_required
@require_POST
def student_status(request, pk):
    user = get_object_or_404(student_qs(), pk=pk)
    action = request.POST.get("action")
    if action == "deactivate":
        changed = set_student_active(user, False)
        if not changed:
            messages.info(request, f"{user.display_name()} was already inactive.")
        elif send_account_status_email(user, False):
            messages.success(request, f"{user.display_name()} can no longer sign in. A suspension email was sent.")
        else:
            messages.warning(request, f"{user.display_name()} can no longer sign in. The status email could not be sent.")
    elif action == "activate":
        changed = set_student_active(user, True)
        if not changed:
            messages.info(request, f"{user.display_name()} was already active.")
        elif send_account_status_email(user, True):
            messages.success(request, f"{user.display_name()} can sign in again. A restoration email was sent.")
        else:
            messages.warning(request, f"{user.display_name()} can sign in again. The status email could not be sent.")
    else:
        messages.error(request, "Choose deactivate or reactivate.")
    return redirect("ops:student", pk=user.pk)


def _course_performance(course):
    learners = student_qs()
    student_n = learners.count()
    completed_ids = set(
        CourseProgress.objects.filter(course=course, user__in=learners).values_list("user_id", flat=True)
    )
    readings = list(ReadingProgress.objects.filter(course=course, user__in=learners))
    opened = set(completed_ids)
    indexes = {}
    for row in readings:
        opened.add(row.user_id)
        indexes[row.user_id] = row.last_page_index
    pages = server_total_pages(course)
    average = None
    if opened and pages:
        scores = []
        for user_id in opened:
            if user_id in completed_ids:
                scores.append(100)
            else:
                reached = indexes.get(user_id, 0) + 1
                scores.append(min(100, round(reached / pages * 100)))
        average = round(sum(scores) / len(scores))
    return {
        "students": student_n,
        "completed": len(completed_ids),
        "readers": len(readings),
        "percent": round(len(completed_ids) / student_n * 100) if student_n else 0,
        "average": average,
        "pages": pages,
    }


@superuser_required
def courses(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    if status not in ("", "published", "draft"):
        status = ""
    ctx = _shell(request, "courses", "Courses")
    ctx.update({
        "rows": manage_course_rows(q, status),
        "summary": course_summary(),
        "q": q,
        "status": status,
    })
    return render(request, "dashboard/ops/courses.html", ctx)


@superuser_required
def course_create(request):
    form = CourseManageForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        course = form.save()
        messages.success(request, f"Course {course.code} was created.")
        return redirect("ops:course_edit", code=course.code)
    ctx = _shell(request, "courses", "Create course")
    ctx.update({"form": form, "course": None})
    return render(request, "dashboard/ops/course_form.html", ctx)


@superuser_required
def course_edit(request, code):
    course = get_object_or_404(Course, code=code)
    form = CourseManageForm(request.POST or None, request.FILES or None, instance=course)
    if request.method == "POST" and form.is_valid():
        course = form.save()
        messages.success(request, f"Course {course.code} was saved.")
        return redirect("ops:course_edit", code=course.code)
    ctx = _shell(request, "courses", course.title)
    ctx.update({
        "form": form,
        "course": course,
        "performance": _course_performance(course),
    })
    return render(request, "dashboard/ops/course_form.html", ctx)


@superuser_required
@require_POST
def course_publish(request, code):
    course = get_object_or_404(Course, code=code)
    action = request.POST.get("action")
    if action == "publish":
        course.is_published = True
        messages.success(request, f"{course.code} is now published.")
    elif action == "unpublish":
        course.is_published = False
        messages.success(request, f"{course.code} is now a draft. Students cannot open it.")
    else:
        messages.error(request, "Choose publish or unpublish.")
    if action in ("publish", "unpublish"):
        course.save(update_fields=["is_published"])
    next_url = request.POST.get("next") or ""
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("ops:courses")


@superuser_required
@require_http_methods(["GET", "HEAD"])
def games(request):
    keys = {item["key"] for item in GAMES_REGISTRY}
    game = request.GET.get("game", "")
    if game not in keys:
        game = ""
    bank_raw = request.GET.get("bank", "")
    bank_id = int(bank_raw) if str(bank_raw).isdigit() else None
    if bank_id is not None and not QuestionBank.objects.filter(pk=bank_id, domain__in=keys).exists():
        bank_id = None
    q = request.GET.get("q", "").strip()
    ctx = _shell(request, "games", "Games")
    ctx.update({
        "games": game_catalog(q, game, bank_id),
        "catalog": [(item["key"], item["name"]) for item in GAMES_REGISTRY],
        "banks": QuestionBank.objects.filter(domain__in=keys).order_by("title"),
        "q": q,
        "game": game,
        "bank": bank_id or "",
    })
    return render(request, "dashboard/ops/games.html", ctx)


@superuser_required
@require_http_methods(["GET", "HEAD"])
def game_page(request, key):
    game = game_detail(key)
    if game is None:
        raise Http404
    ctx = _shell(request, "games", game["name"])
    ctx["game"] = game
    return render(request, "dashboard/ops/game_detail.html", ctx)


@superuser_required
@require_http_methods(["GET", "HEAD"])
def practice(request):
    domain = request.GET.get("domain", "")
    activity = request.GET.get("type", "")
    difficulty = request.GET.get("difficulty", "")
    if domain not in {item["slug"] for item in DOMAINS}:
        domain = ""
    if activity not in {"simulation", "incident"}:
        activity = ""
    if difficulty not in {"beginner", "intermediate", "advanced"}:
        difficulty = ""
    q = request.GET.get("q", "").strip()
    ctx = _shell(request, "practice", "Practice scenarios")
    ctx.update({
        "scenarios": practice_scenario_rows(q, domain, activity, difficulty),
        "domains": [(item["slug"], item["full_label"]) for item in DOMAINS],
        "q": q,
        "domain": domain,
        "activity": activity,
        "difficulty": difficulty,
        "rows": practice_rows(),
        "recent": PracticeSession.objects.select_related("user").order_by("-created_at")[:8],
    })
    return render(request, "dashboard/ops/practice.html", ctx)


@superuser_required
@require_http_methods(["GET", "HEAD"])
def practice_scenario(request, key):
    scenario = practice_scenario_view(key)
    if scenario is None:
        raise Http404
    ctx = _shell(request, "practice", scenario["title"])
    ctx["scenario"] = scenario
    return render(request, "dashboard/ops/practice_scenario.html", ctx)


@superuser_required
def questions(request):
    status = request.GET.get("status", "")
    allowed_status = {value for value, _label in QuestionBank.STATUS_CHOICES}
    if status not in allowed_status:
        status = ""
    domain = request.GET.get("domain", "")
    allowed_domains = {value for value, _label in SET_COURSES}
    if domain not in allowed_domains:
        domain = ""
    q = request.GET.get("q", "").strip()
    ctx = _shell(request, "questions", "Question banks")
    ctx.update({
        "summary": question_summary(),
        "page_obj": _page(request, question_bank_list(q, status, domain)),
        "status": status,
        "domain": domain,
        "q": q,
        "statuses": QuestionBank.STATUS_CHOICES,
        "domains": SET_COURSES,
    })
    return render(request, "dashboard/ops/questions.html", ctx)


@superuser_required
def question_bank_detail(request, pk):
    bank = get_object_or_404(
        QuestionBank.objects.prefetch_related("question_sets__items__question"),
        pk=pk,
    )
    sets = bank.question_sets.all().order_by("set_number")
    ctx = _shell(request, "questions", bank.title)
    ctx.update({"bank": bank, "sets": sets})
    return render(request, "dashboard/ops/question_bank.html", ctx)


@superuser_required
@require_POST
def archive_bank(request, pk):
    bank = get_object_or_404(QuestionBank, pk=pk)
    if bank.status == QuestionBank.STATUS_ARCHIVED:
        messages.error(request, "This question bank is already archived.")
    elif request.POST.get("action") != "archive":
        messages.error(request, "That action is not available.")
    else:
        bank.status = QuestionBank.STATUS_ARCHIVED
        bank.save(update_fields=["status", "updated_at"])
        messages.success(request, f"{bank.title} is archived. Students will no longer receive its questions.")
    return redirect("ops:question_bank", pk=bank.pk)


@superuser_required
def question_detail(request, pk):
    question = get_object_or_404(Question.objects.prefetch_related("sets__question_bank"), pk=pk)
    live = question_reaches_students(question)
    if request.method == "POST":
        if live:
            messages.error(request, "This question is in a live game. Hide it from students before changing the wording.")
            return redirect("ops:question_detail", pk=question.pk)
        form = QuestionTextForm(request.POST)
        if form.is_valid():
            try:
                form.apply(question)
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "Question saved. Students are not receiving this question right now.")
                return redirect("ops:question_detail", pk=question.pk)
        else:
            messages.error(request, "Check the question and try again.")
    else:
        form = QuestionTextForm.from_question(question)
    ctx = _shell(request, "questions", "Question")
    ctx.update({"question": question, "form": form, "live": live})
    return render(request, "dashboard/ops/question_detail.html", ctx)


@superuser_required
@require_POST
def question_visibility(request, pk):
    question = get_object_or_404(Question, pk=pk)
    action = request.POST.get("action")
    if action == "hide":
        question.is_active = False
        question.save(update_fields=["is_active", "updated_at"])
        messages.success(request, "Hidden from students.")
    elif action == "show":
        question.is_active = True
        try:
            question.full_clean()
        except ValidationError:
            question.is_active = False
            messages.error(request, "This question is not ready to show to students.")
        else:
            question.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "Students can receive this question again when its set is approved.")
    else:
        messages.error(request, "That action is not available.")
    return redirect("ops:question_detail", pk=question.pk)


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
@require_http_methods(["GET", "HEAD"])
def certificates(request):
    window = request.GET.get("window", "")
    if window not in ("", "7", "30"):
        window = ""
    readiness = request.GET.get("readiness", "")
    if readiness not in ("", "ready", "incomplete"):
        readiness = ""
    q = request.GET.get("q", "").strip()
    waiting = eligible_students_without_certificate()
    summary = certificate_summary()
    summary["waiting"] = len(waiting)
    ctx = _shell(request, "certificates", "Certificates")
    ctx.update({
        "page_obj": _page(request, certificate_directory(q, window, readiness)),
        "summary": summary,
        "waiting": waiting,
        "q": q,
        "window": window,
        "readiness": readiness,
    })
    return render(request, "dashboard/ops/certificates.html", ctx)


@superuser_required
@require_http_methods(["GET", "HEAD"])
def certificate_detail(request, pk):
    certificate = get_object_or_404(IssuedCertificate.objects.select_related("user"), pk=pk)
    ctx = _shell(request, "certificates", certificate.certificate_id)
    ctx["certificate"] = certificate_detail_context(certificate, request)
    return render(request, "dashboard/ops/certificate.html", ctx)


@superuser_required
@require_POST
def issue_certificate(request, pk):
    from certificates.services.issuance import CertificateIssuanceError, issue_certificate_for_user

    user = get_object_or_404(student_qs(), pk=pk)
    try:
        certificate = issue_certificate_for_user(user, request=request)
    except CertificateIssuanceError as exc:
        messages.error(request, str(exc))
        return redirect("ops:certificates")
    messages.success(request, f"Certificate {certificate.certificate_id} is ready.")
    return redirect("ops:certificate", pk=certificate.pk)


@superuser_required
@require_http_methods(["GET", "HEAD"])
def achievements(request):
    status = request.GET.get("status", "")
    if status not in ("", "active", "inactive"):
        status = ""
    q = request.GET.get("q", "").strip()
    ctx = _shell(request, "achievements", "Achievements")
    ctx.update({
        "badges": achievement_directory(q, status),
        "summary": achievement_summary(),
        "q": q,
        "status": status,
    })
    return render(request, "dashboard/ops/achievements.html", ctx)


@superuser_required
@require_http_methods(["GET", "HEAD"])
def achievement_detail(request, pk):
    badge = get_object_or_404(Badge, pk=pk)
    earners = achievement_earners(badge)
    summary = achievement_summary()
    ctx = _shell(request, "achievements", badge.name)
    ctx.update({
        "badge": badge,
        "earned": earners.count(),
        "latest": earners.aggregate(latest=Max("earned_at"))["latest"],
        "page_obj": _page(request, earners),
        "summary": summary,
    })
    return render(request, "dashboard/ops/achievement.html", ctx)


@superuser_required
@require_http_methods(["GET", "HEAD"])
def leaderboard(request):
    level = request.GET.get("level", "")
    if level != "" and not str(level).isdigit():
        level = ""
    activity = request.GET.get("activity", "")
    if activity not in ("", "recent", "never"):
        activity = ""
    q = request.GET.get("q", "").strip()
    ctx = _shell(request, "leaderboard", "Leaderboard")
    ctx.update({
        "page_obj": _page(request, leaderboard_directory(q, level, activity), per=25),
        "summary": leaderboard_summary(),
        "q": q,
        "level": level,
        "activity": activity,
        "filtered": bool(q or level or activity),
    })
    return render(request, "dashboard/ops/leaderboard.html", ctx)


@superuser_required
@require_http_methods(["GET", "HEAD", "POST"])
def notifications(request):
    form_errors = {}
    posted = {"email": "", "message": "", "link_url": ""}
    if request.method == "POST":
        posted = {
            "email": request.POST.get("email", ""),
            "message": request.POST.get("message", ""),
            "link_url": request.POST.get("link_url", ""),
        }
        note, form_errors = send_student_notification(
            posted["email"], posted["message"], posted["link_url"], request,
        )
        if not form_errors:
            messages.success(request, f"In-app notification saved for {note.user.email}. No email was sent.")
            return redirect("ops:notifications")
    status = request.GET.get("status", "")
    if status not in ("", "read", "unread"):
        status = ""
    window = request.GET.get("window", "")
    if window not in ("", "7", "30"):
        window = ""
    q = request.GET.get("q", "").strip()
    ctx = _shell(request, "notifications", "Notifications")
    ctx.update({
        "page_obj": _page(request, notification_directory(q, status, window)),
        "summary": notification_summary(),
        "q": q,
        "status": status,
        "window": window,
        "form_errors": form_errors,
        "posted": posted,
    })
    return render(request, "dashboard/ops/notifications.html", ctx)


@superuser_required
@require_http_methods(["GET", "HEAD"])
def notification_detail(request, pk):
    note = get_object_or_404(Notification.objects.select_related("user"), pk=pk)
    ctx = _shell(request, "notifications", "Notification")
    ctx.update({
        "note": note,
        "safe_link": _safe_notification_target(request, note.link_url),
        "is_student": not note.user.is_staff and not note.user.is_superuser,
    })
    return render(request, "dashboard/ops/notification.html", ctx)


@superuser_required
@require_http_methods(["GET", "HEAD"])
def contact(request):
    state = request.GET.get("state", "")
    if state not in ("", "open", "resolved"):
        state = ""
    window = request.GET.get("window", "")
    if window not in ("", "7", "30"):
        window = ""
    q = request.GET.get("q", "").strip()
    ctx = _shell(request, "contact", "Contact")
    ctx.update({
        "page_obj": _page(request, contact_directory(q, state, window)),
        "summary": contact_summary(),
        "q": q,
        "state": state,
        "window": window,
    })
    return render(request, "dashboard/ops/contact.html", ctx)


@superuser_required
@require_http_methods(["GET", "HEAD"])
def contact_detail(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    ctx = _shell(request, "contact", msg.name)
    ctx["msg"] = msg
    return render(request, "dashboard/ops/contact_message.html", ctx)


@superuser_required
@require_POST
def reply_contact(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    sent, error = send_contact_reply(msg, request.POST.get("reply", ""))
    if sent:
        messages.success(request, f"Reply sent to {msg.email}.")
    else:
        messages.error(request, error)
    return redirect("ops:contact_message", pk=msg.pk)


@superuser_required
@require_POST
def resolve_contact(request, pk):
    msg = get_object_or_404(ContactMessage, pk=pk)
    choice = request.POST.get("resolved", "")
    if choice in ("0", "1"):
        set_contact_resolved(msg, choice == "1")
    else:
        messages.error(request, "Choose open or resolved.")
    return redirect("ops:contact_message", pk=msg.pk)


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
@require_http_methods(["GET", "HEAD"])
def analytics(request):
    period = request.GET.get("period", "")
    if period not in ("7", "30", "90"):
        period = ""
    ctx = _shell(request, "analytics", "Analytics")
    ctx["report"] = analytics_report(period)
    ctx["period"] = period or "all"
    return render(request, "dashboard/ops/analytics.html", ctx)


@superuser_required
@require_http_methods(["GET", "HEAD", "POST"])
def create_administrator(request):
    errors = {}
    posted = {"email": "", "username": ""}
    if request.method == "POST":
        posted = {
            "email": request.POST.get("email", ""),
            "username": request.POST.get("username", ""),
        }
        user, errors = create_command_superuser(
            posted["email"],
            posted["username"],
            request.POST.get("password", ""),
            request.POST.get("confirm", ""),
        )
        if user is not None:
            messages.success(request, f"Administrator {user.email} was created.")
            return redirect("ops:create_administrator")
    ctx = _shell(request, "settings", "New administrator")
    ctx.update({"errors": errors, "posted": posted})
    return render(request, "dashboard/ops/administrator.html", ctx)


@superuser_required
@require_http_methods(["GET", "HEAD"])
def settings_page(request):
    ctx = _shell(request, "settings", "Settings")
    ctx["groups"] = system_health()
    return render(request, "dashboard/ops/settings.html", ctx)
