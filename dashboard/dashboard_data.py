"""
dashboard/dashboard_data.py
---------------------------
Turns the real dashboard data (utils.get_dashboard_context) into the plain
dicts the bookshelf dashboard template reads: profile, stats, books, skills,
radar, activity, badges, leaderboard, tip and quote.

Nothing here invents numbers. The only fixed values are cosmetic: the hero
quote and the badge frame colours (Badge has no colour field).
"""

from math import cos, radians, sin

from django.urls import reverse

from achievements.models import Badge, UserBadge
from courses.progress import course_for_game
from games.registry import active_games, coming_soon_games

from .mission_styles import style_for

HERO_QUOTE = "Small steps today, stronger cybersecurity tomorrow."
BADGE_COLORS = ["#b45309", "#be123c", "#0e7490", "#6d28d9", "#15803d", "#a21caf"]
LOCKED_BADGE_COLOR = "#2c1766"


def _initials(name):
    parts = (name or "?").split()
    return "".join(part[0] for part in parts[:2]).upper() or "?"


# ---------------------------------------------------------------- profile
def get_profile(user, base):
    level = user.level
    xp_next = level * 100  # level = xp // 100 + 1, so the next level starts here
    avatar_url = reverse("accounts:profile_photo", args=[user.pk]) if base["profile_picture"] else None
    return {
        "name": base["display_name"],
        "initials": _initials(base["display_name"]),
        "avatar_url": avatar_url,
        "level": level,
        "rank_title": base["cyber_class_label"],
        "rank": base["my_rank"],
        "xp": user.xp,
        "xp_next": xp_next,
        "xp_pct": base["xp_progress_percent"],
        "xp_remaining": base["xp_remaining"],
        "streak": base["current_streak"],
        "badge_count": base["total_badges_earned"],
    }


# ---------------------------------------------------------------- missions
def get_missions(base):
    """One book per mission: the eight active ones, then the Coming Soon ones."""
    descriptions = {game["key"]: game["description"] for game in active_games() + coming_soon_games()}
    books = []
    position = 0
    for mission in base["active_missions"]:
        position += 1
        pct = mission["progress"] if mission["attempted"] else 0
        if mission["locked"]:
            # Unlocked by finishing its course: send the student to that course.
            course = course_for_game(mission["key"])
            url = reverse("courses:detail", args=[course.code]) if course else reverse("courses:intro")
            status, cta = "course", "Read the course"
        else:
            url = reverse(mission["url_name"])
            if not mission["attempted"]:
                status, cta = "new", "Start"
            elif pct >= 100:
                status, cta = "done", "Replay"
            else:
                status, cta = "progress", "Replay"
        books.append({
            "key": mission["key"],
            "code": f"{position:02d}",
            "title": mission["name"],
            "description": descriptions.get(mission["key"], ""),
            "percent": pct,
            "percent_label": f"{pct}%" if mission["attempted"] else "—",
            "status": status,
            "cta": cta,
            "locked": False,
            "course_locked": mission["locked"],
            "url": url,
            **style_for(position),
        })
    for mission in base["coming_soon_missions"]:
        position += 1
        books.append({
            "key": "",
            "code": f"{position:02d}",
            "title": mission["name"],
            "description": "Opens with its course in a future update.",
            "percent": 0,
            "percent_label": "—",
            "status": "locked",
            "cta": "Coming soon",
            "locked": True,
            "course_locked": False,
            "url": "",
            **style_for(position, locked=True),
        })
    return books


# ---------------------------------------------------------------- skills + radar
def get_skills(books):
    """One skill per active mission, using the best score."""
    return [{"name": b["title"], "percent": b["percent"]} for b in books if not b["locked"]]


def radar_points(skills, size=220, radius=96):
    """SVG polygon point strings for the radar grid and the value shape."""
    n = len(skills) or 1
    c = size / 2

    def poly(values):
        pts = []
        for i, v in enumerate(values):
            a = radians(-90 + i * 360 / n)
            r = radius * v
            pts.append(f"{c + r * cos(a):.1f},{c + r * sin(a):.1f}")
        return " ".join(pts)

    return {
        "rings": [poly([f] * n) for f in (1, 0.75, 0.5, 0.25)],
        "values": poly([max(s["percent"] / 100, 0.05) for s in skills]),
    }


# ---------------------------------------------------------------- side panels
def get_stats(profile, base):
    return [
        {"value": f"{base['missions_completed']}/{base['total_missions']}", "label": "Missions"},
        {"value": profile["streak"], "label": "Day Streak"},
        {"value": f"{base['average_score']}%", "label": "Avg. Score"},
        {"value": f"{base['skills_mastered']}/{base['total_missions']}", "label": "Skills Mastered"},
    ]


def get_activity(base):
    return [
        {"kind": "badge" if item["kind"] == "badge" else "done",
         "text": item["text"], "xp": item.get("xp") or 0, "when": item["at"]}
        for item in base["recent_activity"]
    ]


def get_badges(user):
    """The four latest badges; if fewer, the next badge still to earn is shown locked."""
    earned = list(
        UserBadge.objects.filter(user=user).select_related("badge").order_by("-earned_at")[:4]
    )
    badges = [
        {"name": ub.badge.name, "icon": ub.badge.icon_emoji,
         "color": BADGE_COLORS[i % len(BADGE_COLORS)], "locked": False}
        for i, ub in enumerate(earned)
    ]
    if len(badges) < 4:
        upcoming = (
            Badge.objects.filter(is_active=True)
            .exclude(awarded_to__user=user)
            .order_by("id")[: 4 - len(badges)]
        )
        badges += [
            {"name": badge.name, "icon": "", "color": LOCKED_BADGE_COLOR, "locked": True}
            for badge in upcoming
        ]
    return badges


def get_leaderboard(user, base):
    rows = []
    for rank, person in enumerate(base["top_users"], start=1):
        name = person.username or person.display_name()
        rows.append({
            "rank": rank,
            "name": name,
            "xp": person.xp,
            "initial": (name[:1] or "?").upper(),
            "avatar_url": reverse("accounts:profile_photo", args=[person.pk]) if person.profile_picture else None,
            "is_me": person.pk == user.pk,
        })
    return rows


def build_dashboard_context(user, base):
    """`base` is utils.get_dashboard_context(user); its keys stay available too."""
    profile = get_profile(user, base)
    books = get_missions(base)
    skills = get_skills(books)
    return {
        "profile": profile,
        "stats": get_stats(profile, base),
        "books": books,
        "skills": skills,
        "radar": radar_points(skills),
        "activity": get_activity(base),
        "badges": get_badges(user),
        "leaderboard": get_leaderboard(user, base),
        "tip": base["cyber_tip"],
        "quote": HERO_QUOTE,
    }
