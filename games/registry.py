# Display order is fixed and follows the eight-course defence curriculum:
# mission N is unlocked by finishing course N (see courses.progress).
#
# Keys are permanent: they are stored on every GameAttempt, badge check,
# certificate and question bank. Existing missions keep their old keys
# (e.g. password_cracker) even though their names changed.
#
# Coming Soon missions belong to the Coming Soon courses. They show as locked
# cards below the active missions, can't be started, and don't count toward
# totals or certificates. Past attempts keep their names.
GAMES_REGISTRY = [
    {"key": "online_safety", "name": "Online Safety Patrol", "card_name": "Online Safety",
     "description": "Spot risky sites, fake alerts and oversharing before they catch you.",
     "url_name": "games:online_safety", "emoji": "🌐"},
    {"key": "phishing_simulator", "name": "Phishing Simulator", "card_name": "Phishing & Scams",
     "description": "Spot the fake emails before they get you.", "url_name": "games:phishing_simulator", "emoji": "📧"},
    {"key": "password_cracker", "name": "Account Protection Challenge", "card_name": "Account Protection",
     "description": "Choose strong passphrases, MFA and safe recovery steps.",
     "url_name": "games:password_cracker", "emoji": "🔑"},
    {"key": "malware_defense", "name": "Malware Defence Drill", "card_name": "Malware Defence",
     "description": "Handle risky downloads, antivirus alerts and ransomware safely.",
     "url_name": "games:malware_defense", "emoji": "🦠"},
    {"key": "network_defense", "name": "Wi-Fi & Network Defence", "card_name": "Wi-Fi & Network",
     "description": "Secure the router and make safe choices on public Wi-Fi.",
     "url_name": "games:network_defense", "emoji": "📶"},
    {"key": "device_protection", "name": "Device Lockdown", "card_name": "Device Protection",
     "description": "Lock, update, back up and recover your devices and files.",
     "url_name": "games:device_protection", "emoji": "📱"},
    {"key": "privacy_defense", "name": "Privacy Shield", "card_name": "Privacy Shield",
     "description": "Protect your profile, photos and identity on social media.",
     "url_name": "games:privacy_defense", "emoji": "👤"},
    {"key": "incident_response", "name": "Incident Response Drill", "card_name": "Incident Response",
     "description": "Contain an attack, report it and recover safely.",
     "url_name": "games:incident_response", "emoji": "🚨"},

    # Coming Soon, like their courses.
    {"key": "cryptography", "name": "Cryptography Challenge", "card_name": "Cryptography",
     "description": "Test your understanding of encryption, hashing, and classic ciphers.",
     "url_name": "games:cryptography", "emoji": "🔐", "coming_soon": True},
    {"key": "steganography", "name": "Steganography Hunt", "card_name": "Steganography",
     "description": "The art of hiding information in plain sight.",
     "url_name": "games:steganography", "emoji": "🖼️", "coming_soon": True},
    {"key": "osint", "name": "OSINT Investigation", "card_name": "OSINT",
     "description": "Open-source investigation.", "url_name": "games:osint", "emoji": "🕵️", "coming_soon": True},
]


def game_by_key(key):
    for game in GAMES_REGISTRY:
        if game["key"] == key:
            return game
    return None


def active_games():
    """The eight curriculum missions (dashboard cards, skill matrix, search)."""
    return [game for game in GAMES_REGISTRY if not game.get("coming_soon")]


def coming_soon_games():
    """Locked missions shown below the active ones. Never started."""
    return [game for game in GAMES_REGISTRY if game.get("coming_soon")]


def playable_games():
    """Missions that can be opened: the active ones."""
    return active_games()
