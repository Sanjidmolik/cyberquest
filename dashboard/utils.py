"""
dashboard/utils.py
---------------------
ONE JOB: gather every real number the dashboard displays. Kept separate
from views.py so the view stays a thin "fetch + render" wrapper, and so
these calculations are easy to find/adjust in one place.

Every stat here is computed from REAL data already in the database --
nothing is a placeholder. Where the redesign brief asked for something
we don't actually track (e.g. a login "day streak" or a weekly-reset
leaderboard), it's substituted with the closest real metric instead of
being faked -- see the comments below.
"""

import random
from django.contrib.auth import get_user_model

from games.models import GameAttempt
from games.registry import GAMES_REGISTRY, active_games, coming_soon_games, playable_games
from achievements.models import UserBadge
from notifications.models import Notification
from courses.progress import unlocked_game_keys

UserModel = get_user_model()

# Mission card colours, cycling through the six accent colours in course order.
GAME_THEME_COLORS = {
    "online_safety": "green",
    "phishing_simulator": "cyan",
    "password_cracker": "purple",
    "malware_defense": "amber",
    "network_defense": "teal",
    "device_protection": "rose",
    "privacy_defense": "green",
    "incident_response": "cyan",
}

CYBER_TIPS = [
    "Always verify the sender's actual email address, not just the display name.",
    "A padlock icon means the connection is encrypted -- it does NOT mean the site is trustworthy.",
    "Reusing a password across sites means one breach can compromise every account that shares it.",
    "Legitimate organizations never ask you to confirm a password over email.",
    "Hover over a link before clicking to see where it actually leads.",
]


def get_dashboard_context(user):
    """Build the full context dict the dashboard template needs."""

    # ---- Level / XP ----
    xp_into_level = user.xp % 100
    xp_needed_for_next = 100
    xp_progress_percent = min(xp_into_level, 100)
    xp_remaining = xp_needed_for_next - xp_into_level

    # ---- Leaderboard rank (reuses the same ordering as the Leaderboard page) ----
    ranked_ids = list(
        UserModel.objects.filter(is_active=True)
        .exclude(username__isnull=True).exclude(username="")
        .order_by("-xp").values_list("id", flat=True)
    )
    my_rank = (ranked_ids.index(user.id) + 1) if user.id in ranked_ids else None

    # ---- Per-game best attempt (used for both Active Missions and Skill Matrix) ----
    attempts = GameAttempt.objects.filter(user=user).finished()
    best_by_game = {}
    for attempt in attempts:
        pct = (attempt.score / attempt.total_questions * 100) if attempt.total_questions else 0
        if attempt.game_key not in best_by_game or pct > best_by_game[attempt.game_key]:
            best_by_game[attempt.game_key] = round(pct)

    playable_keys = {game["key"] for game in playable_games()}
    played_scores = {key: pct for key, pct in best_by_game.items() if key in playable_keys}
    missions_completed = len(played_scores)
    total_missions = len(playable_keys)

    # "Average Score" = average of best-attempt percentages across playable games actually played.
    average_score = round(sum(played_scores.values()) / len(played_scores)) if played_scores else 0

    # "Skills Mastered" = playable games where the best attempt was 80%+ correct.
    skills_mastered = sum(1 for pct in played_scores.values() if pct >= 80)

    # Each mission unlocks on its own once its course is completed (admins: all).
    unlocked_keys = unlocked_game_keys(user)
    missions_locked = not (unlocked_keys & playable_keys)

    active_missions = []
    for index, game in enumerate(active_games(), start=1):
        progress = best_by_game.get(game["key"], 0)
        coming_soon = bool(game.get("coming_soon"))
        active_missions.append({
            "number": f"{index:02d}",
            "key": game["key"],
            "name": game.get("card_name") or game["name"],
            "emoji": game["emoji"],
            "url_name": game.get("url_name") or "",
            "progress": 0 if coming_soon else progress,
            "color": GAME_THEME_COLORS.get(game["key"], "green"),
            "attempted": (not coming_soon) and game["key"] in best_by_game,
            "coming_soon": coming_soon,
            "locked": (not coming_soon) and game["key"] not in unlocked_keys,
        })

    # ---- Skill matrix (same best-attempt data, relabeled for the panel) ----
    skill_matrix = [
        {"label": game.get("card_name") or game["name"],
         "percent": 0 if game.get("coming_soon") else best_by_game.get(game["key"], 0),
         "color": GAME_THEME_COLORS.get(game["key"], "green"),
         "coming_soon": bool(game.get("coming_soon"))}
        for game in active_games()
    ]

    # ---- Recent activity: real game attempts + real badge unlocks, merged by time ----
    recent_attempts = [
        {"kind": "mission", "text": f"Completed: {dict((g['key'], g['name']) for g in GAMES_REGISTRY).get(a.game_key, a.game_key)}",
         "xp": a.xp_awarded, "at": a.completed_at}
        for a in attempts.order_by("-completed_at")[:5]
    ]
    recent_badges = [
        {"kind": "badge", "text": f"Earned badge: {ub.badge.name}", "xp": 0, "at": ub.earned_at}
        for ub in UserBadge.objects.filter(user=user).select_related("badge").order_by("-earned_at")[:5]
    ]
    recent_activity = sorted(recent_attempts + recent_badges, key=lambda x: x["at"], reverse=True)[:3]

    # ---- Notifications (real) ----
    all_notifications = Notification.objects.filter(user=user)
    unread_notification_count = all_notifications.filter(is_read=False).count()
    notifications = all_notifications.order_by("-created_at")[:3]

    total_badges_earned = UserBadge.objects.filter(user=user).count()

    # ---- Real login streak (tracked via CustomUser.record_daily_activity(),
    # called on every successful login) ----
    current_streak = user.current_streak

    # ---- Leaderboard preview (top 5 + this user if outside it) ----
    top_users = list(
        UserModel.objects.filter(is_active=True)
        .exclude(username__isnull=True).exclude(username="")
        .order_by("-xp")[:5]
    )

    return {
        "display_name": user.display_name(),
        "username": user.username,
        "cyber_class_label": user.get_cyber_class_display(),
        "profile_picture": user.profile_picture,
        "level": user.level,
        "xp": user.xp,
        "xp_progress_percent": xp_progress_percent,
        "xp_remaining": xp_remaining,
        "xp_needed_for_next": xp_needed_for_next,
        "my_rank": my_rank,
        "missions_completed": missions_completed,
        "total_missions": total_missions,
        "average_score": average_score,
        "skills_mastered": skills_mastered,
        "missions_locked": missions_locked,
        "active_missions": active_missions,
        "coming_soon_missions": [
            {"name": game.get("card_name") or game["name"], "emoji": game["emoji"]}
            for game in coming_soon_games()
        ],
        "skill_matrix": skill_matrix,
        "recent_activity": recent_activity,
        "notifications": notifications,
        "unread_notification_count": unread_notification_count,
        "total_badges_earned": total_badges_earned,
        "current_streak": current_streak,
        "top_users": top_users,
        "cyber_tip": random.choice(CYBER_TIPS),
    }
