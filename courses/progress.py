from .models import Course, CourseProgress


def has_completed_all_courses(user) -> bool:
    total = Course.objects.filter(is_published=True).count()
    if total == 0:
        return True
    done = CourseProgress.objects.filter(user=user, course__is_published=True).count()
    return done >= total


def completed_course_count(user):
    total = Course.objects.filter(is_published=True).count()
    done = CourseProgress.objects.filter(user=user, course__is_published=True).count()
    return done, total
