"""
Adaptive engine: Cyber DNA, recommendations, difficulty.
Reuses certificate competency category map + GameAttempt stats;
blends completed PracticeSession scores carefully.
"""

from certificates.competency import competency_band, get_competency_profile
from games.stats import get_best_attempt_percentages

from .models import PracticeSession
from .scenarios import DOMAINS, DOMAIN_SCENARIO


def practice_level_label(score: int) -> str:
    """Reuse shared competency bands from certificates.competency."""
    return competency_band(score)


def recommended_difficulty(score: int) -> str:
    if score >= 85:
        return "advanced"
    if score >= 70:
        return "intermediate"
    return "beginner"


def _best_practice_by_domain(user) -> dict:
    """Best completed practice percent per domain slug."""
    best = {}
    qs = PracticeSession.objects.filter(user=user, status="completed")
    for row in qs.only("domain", "score", "max_score"):
        pct = row.percent
        if row.domain not in best or pct > best[row.domain]:
            best[row.domain] = pct
    return best


def get_domain_competencies(user) -> list:
    """
    Per-domain competency for Practice / Cyber DNA.
    Uses max(game best, practice best) so practice can raise a weak domain
    without inventing a second scoring system. Certificate profile stays
    game-based via get_competency_profile().
    """
    game_best = get_best_attempt_percentages(user)
    practice_best = _best_practice_by_domain(user)

    rows = []
    for domain in DOMAINS:
        game_pct = game_best.get(domain["game_key"], 0)
        prac_pct = practice_best.get(domain["slug"], 0)
        # Prefer the stronger evidence of skill; if neither, 0.
        percent = max(game_pct, prac_pct)
        level = practice_level_label(percent)
        difficulty = recommended_difficulty(percent)
        activity = _recommend_activity_type(percent)
        rows.append({
            **domain,
            "percent": percent,
            "game_percent": game_pct,
            "practice_percent": prac_pct,
            "level": level,
            "difficulty": difficulty,
            "difficulty_label": difficulty.title(),
            "activity": activity,
            "activity_label": _activity_label(domain, activity),
            "scenario_key": DOMAIN_SCENARIO.get(domain["slug"]),
        })
    return rows


def _recommend_activity_type(percent: int) -> str:
    if percent >= 85:
        return "incident"
    if percent >= 70:
        return "simulation"
    return "simulation"


def _activity_label(domain, activity: str) -> str:
    name = domain["full_label"]
    if activity == "incident":
        return f"{name} Incident"
    if activity == "game":
        return f"{name} Game"
    return f"{name} Simulation"


def get_cyber_dna(user) -> dict:
    domains = get_domain_competencies(user)
    overall = round(sum(d["percent"] for d in domains) / len(domains)) if domains else 0
    strongest = max(domains, key=lambda d: d["percent"]) if domains else None
    weakest = min(domains, key=lambda d: d["percent"]) if domains else None
    return {
        "domains": domains,
        "overall": overall,
        "overall_level": practice_level_label(overall),
        "strongest": strongest,
        "weakest": weakest,
        # Certificate-compatible profile (games-only) for reference / non-breakage
        "certificate_profile": get_competency_profile(user),
    }


def get_recommendation(user) -> dict:
    dna = get_cyber_dna(user)
    weakest = dna["weakest"]
    if not weakest:
        return {}

    activity = weakest["activity"]
    difficulty = weakest["difficulty"]
    reason = f"{weakest['full_label']} is currently your weakest competency."

    return {
        "domain": weakest,
        "domain_slug": weakest["slug"],
        "activity": activity,
        "activity_label": weakest["activity_label"],
        "difficulty": difficulty,
        "difficulty_label": difficulty.title(),
        "reason": reason,
        "percent": weakest["percent"],
        "scenario_key": weakest["scenario_key"],
        "overall": dna["overall"],
        "overall_level": dna["overall_level"],
    }


def build_practice_center_context(user) -> dict:
    domains = get_domain_competencies(user)
    recommendation = get_recommendation(user)
    dna = get_cyber_dna(user)
    return {
        "domains": domains,
        "recommendation": recommendation,
        "cyber_dna": dna,
    }
