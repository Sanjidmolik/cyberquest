"""
games/stats.py
------------------
ONE JOB: compute a user's best-attempt percentage per game. Used by
BOTH the dashboard's Skill Matrix and the certificate's Cyber Competency
Profile -- factored out here so those two places can never quietly show
different numbers for the same thing.
"""

from .models import GameAttempt


def get_best_attempt_percentages(user) -> dict:
    """Returns {game_key: best_percentage_int} for every game the user has played."""
    attempts = GameAttempt.objects.filter(user=user)
    best_by_game = {}
    for attempt in attempts:
        pct = (attempt.score / attempt.total_questions * 100) if attempt.total_questions else 0
        if attempt.game_key not in best_by_game or pct > best_by_game[attempt.game_key]:
            best_by_game[attempt.game_key] = round(pct)
    return best_by_game