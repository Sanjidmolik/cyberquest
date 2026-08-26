"""
Seeds the 6 initial badges. An admin can add more later via /admin/ --
just remember to also add a matching check_<code>() function in
achievements/checks.py for it to be auto-awarded (or leave it out and
award it manually via the admin panel).
"""

from django.db import migrations

INITIAL_BADGES = [
    {"code": "first_steps", "name": "First Steps", "icon_emoji": "🎯",
     "description": "Completed your first training game."},
    {"code": "phishing_expert", "name": "Phishing Expert", "icon_emoji": "📧",
     "description": "Scored a perfect 5/5 on the Phishing Simulator."},
    {"code": "password_pro", "name": "Password Pro", "icon_emoji": "🔑",
     "description": "Scored a perfect 5/5 on the Password Cracker Challenge."},
    {"code": "dedicated_learner", "name": "Dedicated Learner", "icon_emoji": "📚",
     "description": "Played every available training game at least once."},
    {"code": "course_complete", "name": "Course Complete", "icon_emoji": "🎓",
     "description": "Completed all training courses."},
    {"code": "level_up", "name": "Rising Star", "icon_emoji": "⭐",
     "description": "Reached Level 3."},
]


def seed_badges(apps, schema_editor):
    Badge = apps.get_model("achievements", "Badge")
    for data in INITIAL_BADGES:
        Badge.objects.get_or_create(code=data["code"], defaults=data)


def remove_badges(apps, schema_editor):
    Badge = apps.get_model("achievements", "Badge")
    codes = [b["code"] for b in INITIAL_BADGES]
    Badge.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [("achievements", "0001_initial")]
    operations = [migrations.RunPython(seed_badges, reverse_code=remove_badges)]
