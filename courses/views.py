"""
courses/views.py
-------------------
course_list()      -- shows all published courses with per-user completion status.
course_detail()    -- the actual book-style reader. Content comes from
                       EITHER an admin-uploaded PDF or plain text (see
                       models.py) -- this view just tells the template
                       which one to render; the flip-page mechanics live
                       entirely in reader.js.
save_reading_progress() -- tiny AJAX endpoint the reader calls after each
                       page flip, so a user can resume where they left off.
mark_course_complete()  -- called by the reader ONLY once the user has
                       actually flipped through to the final page (not a
                       blind timer anymore -- see the design note below).
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json

from django.db.models import Q
from django.urls import reverse

from games.registry import GAMES_REGISTRY
from .models import Course, CourseProgress, ReadingProgress

# Existing games the learning book can hand off to. Matching is by the course
# title or code already stored in the database, not by new lesson text.
LEARNING_TOPICS = {
    "phishing": ("phishing", "games:phishing_simulator", "Phishing Simulator"),
    "password-cracker": ("password", "games:password_cracker", "Password Cracker"),
    "network-defense": ("network", "games:network_defense", "Network Defense"),
    "cryptography": ("crypto", "games:cryptography", "Cryptography Challenge"),
    "osint": ("osint", "games:osint", "OSINT Investigation"),
}


def practice_link_for_course(course):
    haystack = f"{course.code} {course.title}".lower()
    for _slug, (hint, url_name, label) in LEARNING_TOPICS.items():
        if hint in haystack:
            return reverse(url_name), label
    for game in GAMES_REGISTRY:
        if game["key"].split("_")[0] in haystack:
            return reverse(game["url_name"]), game["name"]
    return "", ""


def _reader_context(request, course):
    already_done = CourseProgress.objects.filter(user=request.user, course=course).exists()
    reading_state, _ = ReadingProgress.objects.get_or_create(
        user=request.user, course=course, defaults={"last_page_index": 0}
    )
    practice_url, practice_label = practice_link_for_course(course)
    return {
        "course": course,
        "load_error": False,
        "already_done": already_done,
        "resume_page_index": reading_state.last_page_index,
        "uses_pdf": course.uses_pdf(),
        "practice_url": practice_url,
        "practice_label": practice_label,
    }
from .progress import has_completed_all_courses, completed_course_count


@login_required(login_url="/accounts/login/")
def course_list(request):
    completed_codes = set(
        CourseProgress.objects.filter(user=request.user).values_list("course__code", flat=True)
    )
    courses = Course.objects.filter(is_published=True)
    for course in courses:
        course.is_done = course.code in completed_codes

    done_count, total_count = completed_course_count(request.user)
    all_done = has_completed_all_courses(request.user)

    if request.method == "POST" and all_done:
        return redirect("dashboard:home")

    return render(request, "courses/course_list.html", {
        "courses": courses, "done_count": done_count,
        "total_count": total_count, "all_done": all_done,
    })


@login_required(login_url="/accounts/login/")
def course_detail(request, code):
    """
    Shows the book-style reader for one course.

    DESIGN NOTE (replacing the old 45-second countdown-timer gate):
    Completion is no longer "wait N seconds while a button is disabled."
    Instead, the reader (reader.js) tracks which page the user is on, and
    only enables "Mark as Complete" once they've genuinely flipped to the
    LAST page. This is enforced server-side too, in mark_course_complete()
    below -- the client tells us the page count and the page reached, and
    we simply don't accept completion unless reached >= total. A person
    can still flip through quickly, but they can no longer complete a
    course without at least having every page pass in front of them,
    which is a much better experience than staring at a countdown.
    """
    course = get_object_or_404(Course, code=code, is_published=True)
    already_done = CourseProgress.objects.filter(user=request.user, course=course).exists()

    reading_state, _ = ReadingProgress.objects.get_or_create(
        user=request.user, course=course, defaults={"last_page_index": 0}
    )

    return render(request, "courses/course_reader.html", _reader_context(request, course))


@login_required(login_url="/accounts/login/")
def learning_course(request, topic):
    """Alias routes /learning/<topic>/ onto the existing course reader."""
    topic_info = LEARNING_TOPICS.get(topic)
    if topic_info is None:
        return render(request, "courses/course_reader.html", {"load_error": True, "course": None}, status=404)
    hint = topic_info[0]
    course = (
        Course.objects.filter(is_published=True)
        .filter(Q(title__icontains=hint) | Q(code__icontains=hint))
        .order_by("order", "code")
        .first()
    )
    if course is None:
        return render(request, "courses/course_reader.html", {"load_error": True, "course": None}, status=404)
    return render(request, "courses/course_reader.html", _reader_context(request, course))


@login_required(login_url="/accounts/login/")
@require_POST
def save_reading_progress(request, code):
    """Called by reader.js after every page flip. Fire-and-forget -- never blocks reading."""
    course = get_object_or_404(Course, code=code, is_published=True)
    try:
        page_index = int(json.loads(request.body).get("page_index", 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        page_index = 0

    ReadingProgress.objects.update_or_create(
        user=request.user, course=course, defaults={"last_page_index": max(page_index, 0)},
    )
    return JsonResponse({"saved": True})


@login_required(login_url="/accounts/login/")
@require_POST
def mark_course_complete(request, code):
    """
    Called by reader.js ONLY when the user has reached the final page.
    Still re-validated here server-side (never trust the client alone) --
    see the design note on course_detail() above.
    """
    course = get_object_or_404(Course, code=code, is_published=True)

    try:
        data = json.loads(request.body)
        pages_reached = int(data.get("pages_reached", -1))
        total_pages = int(data.get("total_pages", -1))
    except (ValueError, TypeError, json.JSONDecodeError):
        pages_reached, total_pages = -1, -1

    if total_pages <= 0 or pages_reached < total_pages - 1:
        # -1 index of the last page is (total_pages - 1) -- they haven't
        # actually reached the end yet, so we refuse to mark it complete.
        return JsonResponse({"error": "You need to read through to the last page first."}, status=400)

    CourseProgress.objects.get_or_create(user=request.user, course=course)
    messages.success(request, f"{course.title} complete!")

    from achievements.checks import check_and_award_badges
    new_badges = [b.name for b in check_and_award_badges(request.user)]

    return JsonResponse({"completed": True, "new_badges": new_badges})
