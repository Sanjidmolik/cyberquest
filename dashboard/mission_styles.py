"""
Visual styles for each mission book on the dashboard shelf.

Kept in a separate file so no database migration is needed.
The key is the mission's position (1, 2, 3 ...) in games.registry order.

icon must be one of: globe, mail, key, bug, wifi, phone, eye, siren, lock
"""

MISSION_STYLES = {
    1: {"cover_top": "#2f6fe0", "cover_bottom": "#1a2f80", "accent": "#93c5fd", "icon": "globe"},
    2: {"cover_top": "#d0305f", "cover_bottom": "#6e1230", "accent": "#f9a8d4", "icon": "mail"},
    3: {"cover_top": "#c98512", "cover_bottom": "#6b3a07", "accent": "#fcd34d", "icon": "key"},
    4: {"cover_top": "#0f8f6a", "cover_bottom": "#063f33", "accent": "#6ee7b7", "icon": "bug"},
    5: {"cover_top": "#7c3aed", "cover_bottom": "#36106e", "accent": "#c4b5fd", "icon": "wifi"},
    6: {"cover_top": "#d9601a", "cover_bottom": "#6b2508", "accent": "#fdba74", "icon": "phone"},
    7: {"cover_top": "#a62bb8", "cover_bottom": "#4a0f5c", "accent": "#f0abfc", "icon": "eye"},
    8: {"cover_top": "#c92a2a", "cover_bottom": "#5c0d0d", "accent": "#fca5a5", "icon": "siren"},
}

LOCKED_STYLE = {"cover_top": "#4b5568", "cover_bottom": "#1f2533", "accent": "#94a3b8", "icon": "lock"}
DEFAULT_STYLE = {"cover_top": "#6d28d9", "cover_bottom": "#2e1065", "accent": "#c4b5fd", "icon": "lock"}


def style_for(position, locked=False):
    if locked:
        return LOCKED_STYLE
    return MISSION_STYLES.get(position, DEFAULT_STYLE)
