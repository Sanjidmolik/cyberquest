from .models import Badge, UserBadge


def _perfect_score(user, game_key):
    from games.models import GameAttempt
    return GameAttempt.objects.filter(user=user, game_key=game_key, score=5, total_questions=5).exists()


def check_first_steps(user):
    from games.models import GameAttempt
    return GameAttempt.objects.filter(user=user).exists()


def check_phishing_expert(user):
    return _perfect_score(user, "phishing_simulator")


def check_password_pro(user):
    return _perfect_score(user, "password_cracker")


def check_crypto_cracker(user):
    return _perfect_score(user, "cryptography")


def check_osint_investigator(user):
    return _perfect_score(user, "osint")


def check_ghost_hunter(user):
    return _perfect_score(user, "steganography")


def check_network_guardian(user):
    return _perfect_score(user, "network_defense")


def check_dedicated_learner(user):
    from games.models import GameAttempt
    from games.registry import playable_games
    played = set(GameAttempt.objects.filter(user=user).values_list("game_key", flat=True))
    required = {g["key"] for g in playable_games()}
    return required.issubset(played)


def check_course_complete(user):
    from courses.progress import has_completed_all_courses
    return has_completed_all_courses(user)


def check_level_up(user):
    return user.level >= 3


def check_first_lesson(user):
    from courses.models import CourseProgress
    return CourseProgress.objects.filter(user=user, course__is_published=True).exists()


def _completed_practice(user, domain):
    from practice.models import PracticeSession
    return PracticeSession.objects.filter(user=user, domain=domain, status="completed").exists()


def check_phishing_practice(user):
    return _completed_practice(user, "phishing")


def check_password_practice(user):
    return _completed_practice(user, "password")


def check_network_practice(user):
    return _completed_practice(user, "network")


def check_crypto_practice(user):
    return _completed_practice(user, "cryptography")


def check_osint_practice(user):
    return _completed_practice(user, "osint")


def check_steady_practice(user):
    from practice.models import PracticeSession
    return PracticeSession.objects.filter(user=user, status="completed").count() >= 3


def check_ten_games(user):
    from games.models import GameAttempt
    return GameAttempt.objects.filter(user=user).count() >= 10


CHECKS = {
    "first_steps": check_first_steps,
    "phishing_expert": check_phishing_expert,
    "password_pro": check_password_pro,
    "crypto_cracker": check_crypto_cracker,
    "osint_investigator": check_osint_investigator,
    "ghost_hunter": check_ghost_hunter,
    "network_guardian": check_network_guardian,
    "dedicated_learner": check_dedicated_learner,
    "course_complete": check_course_complete,
    "level_up": check_level_up,
    "first_lesson": check_first_lesson,
    "phishing_practice": check_phishing_practice,
    "password_practice": check_password_practice,
    "network_practice": check_network_practice,
    "crypto_practice": check_crypto_practice,
    "osint_practice": check_osint_practice,
    "steady_practice": check_steady_practice,
    "ten_games": check_ten_games,
}


def check_and_award_badges(user) -> list:
    already_earned_ids = set(UserBadge.objects.filter(user=user).values_list("badge_id", flat=True))
    newly_earned = []
    candidate_badges = Badge.objects.filter(is_active=True).exclude(id__in=already_earned_ids)

    for badge in candidate_badges:
        check_function = CHECKS.get(badge.code)
        if check_function is None:
            continue
        if check_function(user):
            UserBadge.objects.create(user=user, badge=badge)
            newly_earned.append(badge)
            from notifications.utils import notify
            notify(user, f"🏆 New badge unlocked: {badge.icon_emoji} {badge.name}!")

    return newly_earned
