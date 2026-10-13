"""XP and level-up domain logic.

Kept separate from views so service modules (attempts.py, practice/views.py)
can import here without creating an inverted view→service dependency.
"""

XP_PER_CORRECT_ANSWER = 20


def apply_xp_and_level_up(user, xp_awarded: int) -> bool:
    """Credit xp_awarded to user, recalculate level, persist, return True if level increased."""
    old_level = user.level
    user.xp += xp_awarded
    user.level = (user.xp // 100) + 1
    user.save(update_fields=["xp", "level"])
    return user.level > old_level
