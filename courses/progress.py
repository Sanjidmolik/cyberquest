from .models import Course, CourseProgress

# Text lessons are paginated in the browser by viewport size. Use a large
# chars-per-page so this is a lower bound (never higher than a typical client
# page count), which blocks forged tiny totals without trapping real readers.
_TEXT_CHARS_PER_PAGE = 5000


def _pdf_page_count(field) -> int:
    """Body pages of a stored e-book, cached by its stored name.

    With remote storage, counting pages means downloading the whole PDF, and
    this runs on every reading-progress save. Stored names are never reused,
    so a cached count cannot belong to a different file.
    """
    from django.core.cache import cache

    from cyberquest.media_access import read_stored_bytes

    key = f"ebook_pages:{field.name}"
    cached = cache.get(key)
    if cached is not None:
        return int(cached)
    try:
        import pymupdf

        data = read_stored_bytes(field)
        if data is None:
            raise FileNotFoundError(field.name)
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            body = max(1, int(doc.page_count))
    except Exception:
        # A missing or unreadable file is not cached, so a later fix is picked up.
        return 1
    cache.set(key, body, 60 * 60 * 24 * 30)
    return body


def server_total_pages(course) -> int:
    """
    Authoritative flip-book page count: 1 cover sheet + body pages.
    PDF body pages come from the stored file; text uses content length as a
    lower-bound estimate (client layout can only add more pages).
    """
    if course.uses_pdf() and course.pdf_file:
        return _pdf_page_count(course.pdf_file) + 1

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
