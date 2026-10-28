"""
certificates/competency.py
------------------------------
ONE JOB: build the "Cyber Competency Profile" data for a certificate --
8 named skill categories (one per curriculum mission) mapped to real game scores, plus an overall
score and level label. Uses games.stats (the SAME function the
dashboard's Skill Matrix uses) so the numbers never disagree.
"""

from games.stats import get_best_attempt_percentages

# The eight curriculum missions, in course order. A certificate needs every
# one of them played. Retired missions (Cryptography, Steganography, OSINT)
# are not part of eligibility; their past scores are kept but not counted.
CATEGORY_MAP = [
    {"label": "Online Safety", "slug": "safety", "game_key": "online_safety", "color": "#14a3a3"},
    {"label": "Phishing & Scams", "slug": "phishing", "game_key": "phishing_simulator", "color": "#ff2ec4"},
    {"label": "Account Protection", "slug": "password", "game_key": "password_cracker", "color": "#ff9800"},
    {"label": "Malware Defence", "slug": "malware", "game_key": "malware_defense", "color": "#e0702b"},
    {"label": "Wi-Fi & Network", "slug": "network", "game_key": "network_defense", "color": "#3aa0ff"},
    {"label": "Device Protection", "slug": "device", "game_key": "device_protection", "color": "#2f8fd8"},
    {"label": "Privacy Shield", "slug": "privacy", "game_key": "privacy_defense", "color": "#d6458f"},
    {"label": "Incident Response", "slug": "response", "game_key": "incident_response", "color": "#d93a3a"},
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