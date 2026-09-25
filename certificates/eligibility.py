"""
certificates/eligibility.py
--------------------------------
ONE JOB: decide whether a user has earned the CyberQuest completion
certificate.

Real requirement for normal users: ALL published courses completed
AND every game in the registry played at least once.

Exception: staff/admin accounts can always generate a certificate,
regardless of progress -- useful for testing and demos without
needing to actually grind through every course and game each time.
"""


def is_eligible_for_certificate(user) -> bool:
    # Admin bypass -- staff accounts can always generate one.
    if user.is_staff or user.is_superuser:
        return True

    from courses.progress import has_completed_all_courses
    from games.models import GameAttempt
    from games.registry import GAMES_REGISTRY

    if not has_completed_all_courses(user):
        return False

    played_keys = set(GameAttempt.objects.filter(user=user).values_list("game_key", flat=True))
    required_keys = {g["key"] for g in GAMES_REGISTRY}

    return required_keys.issubset(played_keys)