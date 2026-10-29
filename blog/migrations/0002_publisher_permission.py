"""Give the Content Publisher group the blog permission (works on a fresh database)."""

from django.contrib.auth.management import create_permissions
from django.db import migrations


def forwards(apps, schema_editor):
    config = apps.get_app_config("blog")
    config.models_module = True
    create_permissions(config, apps=apps, verbosity=0)
    config.models_module = None
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group, _ = Group.objects.get_or_create(name="Content Publisher")
    group.permissions.add(*Permission.objects.filter(content_type__app_label="blog", codename="publish_post"))


def backwards(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.filter(name="Content Publisher").first()
    if group:
        group.permissions.remove(*Permission.objects.filter(content_type__app_label="blog", codename="publish_post"))


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("practice", "0007_studio_groups_and_hashes"),     # creates the Content Publisher group
        ("blog", "0001_initial"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
