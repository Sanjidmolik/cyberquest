"""Create the Practice Studio groups and record the seed hash of every existing scenario."""

import hashlib
import json

from django.contrib.auth.management import create_permissions
from django.db import migrations

EDITOR = "Content Editor"
PUBLISHER = "Content Publisher"
EDITOR_PERMS = ["use_studio", "add_scenario", "change_scenario", "view_scenario"]
PUBLISHER_PERMS = EDITOR_PERMS + ["publish_scenario"]


def _hash(content):
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def forwards(apps, schema_editor):
    # Permissions are normally created after migrate; make sure they exist now.
    config = apps.get_app_config("practice")
    config.models_module = True
    create_permissions(config, apps=apps, verbosity=0)
    config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for name, codenames in ((EDITOR, EDITOR_PERMS), (PUBLISHER, PUBLISHER_PERMS)):
        group, _ = Group.objects.get_or_create(name=name)
        group.permissions.add(*Permission.objects.filter(content_type__app_label="practice", codename__in=codenames))

    Scenario = apps.get_model("practice", "Scenario")
    for row in Scenario.objects.all():
        row.content_hash = _hash(row.content)
        row.save(update_fields=["content_hash"])


def backwards(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name__in=[EDITOR, PUBLISHER]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("practice", "0006_studio"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
