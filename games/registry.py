# Display order is fixed. OSINT stays in the catalog as a non-interactive
# "Coming Soon" card and must not be launched from mission surfaces.
GAMES_REGISTRY = [
    {"key": "phishing_simulator", "name": "Phishing Simulator", "card_name": "Phishing",
     "description": "Spot the fake emails before they get you.", "url_name": "games:phishing_simulator", "emoji": "📧"},
    {"key": "password_cracker", "name": "Password Cracker Challenge", "card_name": "Password Cracker",
     "description": "Learn why weak passwords fail instantly.", "url_name": "games:password_cracker", "emoji": "🔑"},
    {"key": "network_defense", "name": "Network Defense", "card_name": "Network Defence",
     "description": "Simulate defending a live network against intrusion attempts.", "url_name": "games:network_defense", "emoji": "🛡️"},
    {"key": "cryptography", "name": "Cryptography Challenge", "card_name": "Cryptography",
     "description": "Test your understanding of encryption, hashing, and classic ciphers.", "url_name": "games:cryptography", "emoji": "🔐"},
    {"key": "steganography", "name": "Steganography Hunt", "card_name": "Steganography",
     "description": "The art of hiding information in plain sight.", "url_name": "games:steganography", "emoji": "🖼️"},
    {"key": "osint", "name": "OSINT Investigation", "card_name": "OSINT",
     "description": "Open-source investigation is on the way.", "url_name": "", "emoji": "🕵️",
     "coming_soon": True},
]


def game_by_key(key):
    for game in GAMES_REGISTRY:
        if game["key"] == key:
            return game
    return None


def playable_games():
    """Missions that can be opened. Coming-soon entries stay visible only."""
    return [game for game in GAMES_REGISTRY if not game.get("coming_soon")]
