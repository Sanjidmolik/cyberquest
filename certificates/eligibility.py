"""
certificates/eligibility.py
---------------------------
Server-side certificate eligibility from stored GameAttempt results.

Normal users:
  ALL 5 core CyberQuest games completed
  AND overall competency score >= 80%

Staff/admin accounts can always generate a certificate (demo / testing).
"""

from __future__ import annotations

from games.stats import get_best_attempt_percentages

from .competency import CATEGORY_MAP, get_competency_profile

REQUIRED_GAME_KEYS = [c["game_key"] for c in CATEGORY_MAP]
REQUIRED_GAME_COUNT = len(REQUIRED_GAME_KEYS)
MIN_OVERALL_SCORE = 80


def games_completed_count(user) -> int:
    best = get_best_attempt_percentages(user)
    return sum(1 for key in REQUIRED_GAME_KEYS if key in best)


def all_required_games_completed(user) -> bool:
    return games_completed_count(user) >= REQUIRED_GAME_COUNT


def overall_score_for(user) -> int:
    return int(get_competency_profile(user)["overall_score"])


def _is_staff_user(user) -> bool:
    return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))


def is_eligible_for_certificate(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    # Admin / staff bypass for demos and testing.
    if _is_staff_user(user):
        return True
    if not all_required_games_completed(user):
        return False
    return overall_score_for(user) >= MIN_OVERALL_SCORE


def get_eligibility_status(user) -> dict:
    """Rich status payload for the certificate dashboard page."""
    profile = get_competency_profile(user)
    best = get_best_attempt_percentages(user)
    completed = games_completed_count(user)
    overall = int(profile["overall_score"])
    games_ok = completed >= REQUIRED_GAME_COUNT
    score_ok = overall >= MIN_OVERALL_SCORE
    staff = _is_staff_user(user)
    eligible = staff or (games_ok and score_ok)

    if staff and not (games_ok and score_ok):
        message = (
            "Admin access: you can generate a certificate without completing "
            "all challenges."
        )
    elif eligible:
        message = "Congratulations! You are eligible for your CyberQuest Certificate."
    elif not games_ok:
        message = "Complete all CyberQuest challenges to unlock your certificate."
    else:
        message = "You need an overall score of at least 80% to earn the certificate."

    game_rows = []
    for cat in CATEGORY_MAP:
        key = cat["game_key"]
        played = key in best
        game_rows.append({
            "label": cat["label"],
            "game_key": key,
            "completed": played,
            "percent": best.get(key, 0) if played else None,
        })

    return {
        "eligible": eligible,
        "message": message,
        "overall_score": overall,
        "games_completed": completed,
        "games_required": REQUIRED_GAME_COUNT,
        "min_score": MIN_OVERALL_SCORE,
        "games_requirement_met": games_ok or staff,
        "score_requirement_met": score_ok or staff,
        "staff_bypass": staff,
        "level_label": profile["level_label"],
        "categories": profile["categories"],
        "game_rows": game_rows,
    }
