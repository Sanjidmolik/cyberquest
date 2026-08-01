"""
courses/progress.py
----------------------
ONE JOB: determine whether a user has completed every published course.
Kept separate so dashboard/games (which need to check this to decide
whether to let someone in) don't need to import courses' views or models
directly -- just this one small function.
"""

from .models import Course, CourseProgress


def has_completed_all_courses(user) -> bool:
    """True only if the user has a completion record for every published course."""
    total_courses = Course.objects.filter(is_published=True).count()
    if total_courses == 0:
        return True  # no courses configured yet -- don't lock users out forever

    completed_count = CourseProgress.objects.filter(
        user=user, course__is_published=True
    ).count()

    return completed_count >= total_courses


def completed_course_count(user):
    """Returns (completed, total) -- used to show 'X of Y courses complete'."""
    total_courses = Course.objects.filter(is_published=True).count()
    completed_count = CourseProgress.objects.filter(
        user=user, course__is_published=True
    ).count()
    return completed_count, total_courses
