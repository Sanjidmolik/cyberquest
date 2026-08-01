"""
courses/views.py
-------------------
Two views now, instead of one:

  course_list()    -- shows all 5 (admin-managed) courses with per-user
                       completion status. This is the required first
                       stop after login/signup (see accounts/routing.py).
  course_detail()  -- shows ONE course's full content with the reading
                       timer. Marks that single course as complete.

Course CONTENT itself lives entirely in the database (models.py),
managed by admins -- nothing here is hardcoded course text anymore.
"""

import time

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from .models import Course, CourseProgress
from .progress import has_completed_all_courses, completed_course_count

MINIMUM_READ_SECONDS = 45


@login_required(login_url="/accounts/login/")
def course_list(request):
    """Show every published course with a locked/completed badge per user."""

    completed_codes = set(
        CourseProgress.objects.filter(user=request.user).values_list("course__code", flat=True)
    )

    courses = Course.objects.filter(is_published=True)
    for course in courses:
        course.is_done = course.code in completed_codes  # attached for the template only

    done_count, total_count = completed_course_count(request.user)
    all_done = has_completed_all_courses(request.user)

    if request.method == "POST" and all_done:
        # The "Continue to Dashboard" button only submits successfully
        # once every course is marked complete (checked again here,
        # server-side, not just trusted from the template).
        return redirect("dashboard:home")

    return render(request, "courses/course_list.html", {
        "courses": courses,
        "done_count": done_count,
        "total_count": total_count,
        "all_done": all_done,
    })


@login_required(login_url="/accounts/login/")
def course_detail(request, code):
    """Show one course's content, gated by the same read-timer pattern as before."""

    course = get_object_or_404(Course, code=code, is_published=True)
    already_done = CourseProgress.objects.filter(user=request.user, course=course).exists()

    session_key = f"course_shown_at_{course.code}"

    if request.method == "POST":
        shown_at = request.session.get(session_key)
        elapsed = time.time() - shown_at if shown_at else 0

        if elapsed < MINIMUM_READ_SECONDS and not already_done:
            messages.error(request, "Please finish reading before continuing.")
        else:
            CourseProgress.objects.get_or_create(user=request.user, course=course)
            messages.success(request, f"{course.title} complete!")
            return redirect("courses:intro")
    else:
        request.session[session_key] = time.time()

    return render(request, "courses/course_detail.html", {
        "course": course,
        "already_done": already_done,
        "minimum_read_seconds": MINIMUM_READ_SECONDS,
    })
