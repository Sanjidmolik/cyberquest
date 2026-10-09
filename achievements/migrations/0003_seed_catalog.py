"""Add achievement definitions for checks that were not in the first seed."""

from django.db import migrations

EXTRA_BADGES = [
    {"code": "crypto_cracker", "name": "Crypto Cracker", "icon_emoji": "🔐",
     "description": "Scored a perfect 5/5 on the Cryptography Challenge."},
    {"code": "osint_investigator", "name": "OSINT Investigator", "icon_emoji": "🔎",
     "description": "Scored a perfect 5/5 on the OSINT Investigation."},
    {"code": "ghost_hunter", "name": "Ghost Hunter", "icon_emoji": "👻",
     "description": "Scored a perfect 5/5 on Steganography."},
    {"code": "network_guardian", "name": "Network Guardian", "icon_emoji": "🛡️",
     "description": "Scored a perfect 5/5 on Network Defense."},
    {"code": "first_lesson", "name": "First Lesson", "icon_emoji": "📖",
     "description": "Finished one published course."},
    {"code": "phishing_practice", "name": "Phishing Drill", "icon_emoji": "🎣",
     "description": "Completed a phishing practice scenario."},
    {"code": "password_practice", "name": "Password Drill", "icon_emoji": "🔒",
     "description": "Completed a password-security practice scenario."},
    {"code": "network_practice", "name": "Network Drill", "icon_emoji": "🌐",
     "description": "Completed a network-defense practice scenario."},
    {"code": "crypto_practice", "name": "Crypto Drill", "icon_emoji": "🧩",
     "description": "Completed a cryptography practice scenario."},
    {"code": "osint_practice", "name": "OSINT Drill", "icon_emoji": "🛰️",
     "description": "Completed an OSINT practice scenario."},
    {"code": "steady_practice", "name": "Steady Practice", "icon_emoji": "📅",
     "description": "Completed three practice scenarios."},
    {"code": "ten_games", "name": "Ten Missions", "icon_emoji": "🎮",
     "description": "Finished ten game attempts."},
]


def seed_badges(apps, schema_editor):
    Badge = apps.get_model("achievements", "Badge")
    for data in EXTRA_BADGES:
        Badge.objects.get_or_create(code=data["code"], defaults=data)


def remove_badges(apps, schema_editor):
    Badge = apps.get_model("achievements", "Badge")
    Badge.objects.filter(code__in=[row["code"] for row in EXTRA_BADGES]).delete()


class Migration(migrations.Migration):
    dependencies = [("achievements", "0002_seed_badges")]
    operations = [migrations.RunPython(seed_badges, reverse_code=remove_badges)]
