from .models import Course, CourseProgress

# Text lessons are paginated in the browser by viewport size. Use a large
# chars-per-page so this is a lower bound (never higher than a typical client
# page count), which blocks forged tiny totals without trapping real readers.
_TEXT_CHARS_PER_PAGE = 5000


def server_total_pages(course) -> int:
    """
    Authoritative flip-book page count: 1 cover sheet + body pages.
    PDF body pages come from the stored file; text uses content length as a
    lower-bound estimate (client layout can only add more pages).
    """
    if course.uses_pdf() and course.pdf_file:
        try:
            import pymupdf

            from cyberquest.media_access import stored_file_path

            path = stored_file_path(course.pdf_file)
            if path is None:
                raise FileNotFoundError(course.pdf_file.name)
            with pymupdf.open(path) as doc:
                body = max(1, int(doc.page_count))
        except Exception:
            body = 1
        return body + 1

    text = (course.content or "").strip()
    if not text:
        return 2
    body = max(1, (len(text) + _TEXT_CHARS_PER_PAGE - 1) // _TEXT_CHARS_PER_PAGE)
    return body + 1


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
