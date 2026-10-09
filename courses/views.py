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
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_POST
import json

from django.db.models import Q
from django.urls import reverse

from games.registry import GAMES_REGISTRY
from .models import Course, CourseProgress, ReadingProgress
from .progress import (
    completed_course_count,
    has_completed_all_courses,
    server_total_pages,
)

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
    total = server_total_pages(course)
    try:
        page_index = int(json.loads(request.body).get("page_index", 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        page_index = 0

    if page_index < 0:
        page_index = 0

    state, _ = ReadingProgress.objects.get_or_create(
        user=request.user, course=course, defaults={"last_page_index": 0}
    )
    # Small forward steps only (+2 covers two-page landscape spreads).
    max_allowed = state.last_page_index + 2
    if course.uses_pdf():
        max_allowed = min(total - 1, max_allowed)
    else:
        # Text pagination is viewport-defined; keep a hard ceiling against abuse.
        max_allowed = min(max_allowed, 500)
    page_index = min(page_index, max_allowed)

    if page_index > state.last_page_index:
        state.last_page_index = page_index
        state.save(update_fields=["last_page_index", "updated_at"])
    return JsonResponse({"saved": True})


@login_required(login_url="/accounts/login/")
@require_POST
def mark_course_complete(request, code):
    """
    Called by reader.js ONLY when the user has reached the final page.
    Page totals come from the stored course/PDF on the server — client
    ``total_pages`` is ignored.
    """
    course = get_object_or_404(Course, code=code, is_published=True)
    total_pages = server_total_pages(course)

    try:
        data = json.loads(request.body)
        pages_reached = int(data.get("pages_reached", -1))
    except (ValueError, TypeError, json.JSONDecodeError):
        pages_reached = -1

    if pages_reached < 0 or pages_reached > 500:
        return JsonResponse({"error": "You need to read through to the last page first."}, status=400)

    progress = ReadingProgress.objects.filter(user=request.user, course=course).first()
    saved_index = progress.last_page_index if progress else 0

    if course.uses_pdf():
        # Exact server page count (cover + PDF pages). Reject impossible indices.
        if pages_reached >= total_pages or pages_reached < total_pages - 1:
            return JsonResponse(
                {"error": "You need to read through to the last page first."}, status=400
            )
        if saved_index < max(0, total_pages - 2):
            return JsonResponse(
                {"error": "You need to read through to the last page first."}, status=400
            )
    else:
        # Text: server total is a lower bound. Client may have more pages; require
        # at least that bound, with ReadingProgress proving gradual reading.
        if pages_reached < total_pages - 1:
            return JsonResponse(
                {"error": "You need to read through to the last page first."}, status=400
            )
        if saved_index < max(0, pages_reached - 1):
            return JsonResponse(
                {"error": "You need to read through to the last page first."}, status=400
            )

    CourseProgress.objects.get_or_create(user=request.user, course=course)
    messages.success(request, f"{course.title} complete!")

    from achievements.checks import check_and_award_badges
    new_badges = [b.name for b in check_and_award_badges(request.user)]

    return JsonResponse({"completed": True, "new_badges": new_badges})


def _course_for_media(user, code):
    """Published courses for signed-in students. Superusers may open drafts."""
    course = Course.objects.filter(code=code).first()
    if course is None:
        return None
    if course.is_published or user.is_superuser:
        return course
    return None


def _serve_course_field(request, code, field_name):
    course = _course_for_media(request.user, code)
    if course is None:
        raise Http404("Course not found.")
    from cyberquest.media_access import serve_stored_file

    response = serve_stored_file(getattr(course, field_name))
    if response is None:
        raise Http404("File not found.")
    return response


@login_required(login_url="/accounts/login/")
def course_ebook(request, code):
    """PDF bytes for the reader. PDF.js requests this URL with the session cookie."""
    return _serve_course_field(request, code, "pdf_file")


@login_required(login_url="/accounts/login/")
def course_thumbnail(request, code):
    return _serve_course_field(request, code, "thumbnail")
