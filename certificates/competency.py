"""
certificates/competency.py
------------------------------
ONE JOB: build the "Cyber Competency Profile" data for a certificate --
5 named skill categories mapped to real game scores, plus an overall
score and level label. Uses games.stats (the SAME function the
dashboard's Skill Matrix uses) so the numbers never disagree.
"""

from games.stats import get_best_attempt_percentages

# The five playable missions, in catalog order. OSINT is coming soon and
# is not part of certificate eligibility.
CATEGORY_MAP = [
    {"label": "Phishing", "slug": "phishing", "game_key": "phishing_simulator", "color": "#ff2ec4"},
    {"label": "Password Security", "slug": "password", "game_key": "password_cracker", "color": "#ff9800"},
    {"label": "Network Defense", "slug": "network", "game_key": "network_defense", "color": "#3aa0ff"},
    {"label": "Cryptography", "slug": "cryptography", "game_key": "cryptography", "color": "#39ff88"},
    {"label": "Steganography", "slug": "steganography", "game_key": "steganography", "color": "#ff4d8d"},
]


def competency_band(score: int) -> str:
    """Shared competency bands used by certificates and practice."""
    if score >= 90:
        return "EXPERT"
    if score >= 80:
        return "ADVANCED"
    if score >= 70:
        return "COMPETENT"
    return "DEVELOPING"


def get_competency_profile(user) -> dict:
    """Game-based certificate competency profile (unchanged eligibility source)."""
    best_by_game = get_best_attempt_percentages(user)

    categories = [
        {**cat, "percent": best_by_game.get(cat["game_key"], 0)}
        for cat in CATEGORY_MAP
    ]

    overall_score = round(sum(c["percent"] for c in categories) / len(categories)) if categories else 0
    level_label = competency_band(overall_score)

    if overall_score >= 90:
        filled_stars = 5
    elif overall_score >= 80:
        filled_stars = 4
    elif overall_score >= 70:
        filled_stars = 3
    else:
        filled_stars = 1

    return {
        "categories": categories,
        "overall_score": overall_score,
        "level_label": level_label,
        "filled_stars": filled_stars,
    }