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

    text = chapter_text(course) if course.has_chapters else (course.content or "").strip()
    if not text:
        return 2
    body = max(1, (len(text) + _TEXT_CHARS_PER_PAGE - 1) // _TEXT_CHARS_PER_PAGE)
    return body + 1


def chapter_text(course) -> str:
    """Every word a comic course shows, for the server-side page lower bound."""
    parts = []
    for chapter in course.chapters.prefetch_related("panels", "questions"):
        parts.append(chapter.title)
        parts.extend(f"{p.caption} {p.speech_bubble}" for p in chapter.panels.all())
        for q in chapter.questions.all():
            parts.extend([q.prompt, q.options, q.explanation])
    return " ".join(parts).strip()


def active_completions(user):
    return CourseProgress.objects.filter(
        user=user, course__is_published=True, course__is_coming_soon=False
    )


def has_completed_all_courses(user) -> bool:
    total = Course.objects.active().count()
    if total == 0:
        return True
    return active_completions(user).count() >= total


def completed_course_count(user):
    return active_completions(user).count(), Course.objects.active().count()


# Each mission is unlocked by reading its own course. The course is found by
# its stable code first (see courses/curriculum.py), then by a keyword in its
# code or title for databases seeded before the curriculum.
GAME_COURSE_CODES = {
    "online_safety": "CQ-SAFETY",
    "phishing_simulator": "MOD-01",
    "password_cracker": "MOD-02",
    "malware_defense": "CQ-MALWARE",
    "network_defense": "MOD-03",
    "device_protection": "CQ-DEVICE",
    "privacy_defense": "CQ-PRIVACY",
    "incident_response": "CQ-RESPONSE",
}
GAME_COURSE_HINTS = {
    "online_safety": "online safety",
    "malware_defense": "malware",
    "device_protection": "device",
    "privacy_defense": "privacy",
    "incident_response": "response",
    "phishing_simulator": "phish",
    "password_cracker": "password",
    "network_defense": "network",
    "cryptography": "crypt",
    "steganography": "steg",  # matches "Steganography" (not "stego")
    "osint": "osint",
}


def is_admin(user) -> bool:
    return bool(user.is_authenticated and (user.is_superuser or user.is_staff))


def course_for_game(game_key):
    """The open course whose book unlocks this mission, or None.

    A Coming Soon course cannot be read, so it never unlocks its mission.
    """
    from django.db.models import Q

    code = GAME_COURSE_CODES.get(game_key)
    if code:
        course = Course.objects.active().filter(code=code).first()
        if course is not None:
            return course
    hint = GAME_COURSE_HINTS.get(game_key)
    if not hint:
        return None
    return (
        Course.objects.active()
        .filter(Q(code__icontains=hint) | Q(title__icontains=hint))
        .order_by("order", "code")
        .first()
    )


def missions_by_course_id():
    """{course id: registry entry} for every playable mission whose course is open."""
    from games.registry import playable_games

    found = {}
    for game in playable_games():
        course = course_for_game(game["key"])
        if course is not None:
            found.setdefault(course.id, game)
    return found


def is_game_unlocked(user, game_key) -> bool:
    """Admins can always play. Students play a mission once its course is completed."""
    if is_admin(user):
        return True
    course = course_for_game(game_key)
    if course is None:
        return False
    return CourseProgress.objects.filter(user=user, course=course).exists()


def unlocked_game_keys(user):
    from games.registry import playable_games

    return {game["key"] for game in playable_games() if is_game_unlocked(user, game["key"])}
