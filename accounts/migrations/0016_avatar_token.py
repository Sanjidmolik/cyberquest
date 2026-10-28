"""Give every user a random avatar token (added nullable, filled, then made unique)."""

from django.db import migrations, models
from django.utils.crypto import get_random_string

import accounts.models


def fill_tokens(apps, schema_editor):
    User = apps.get_model("accounts", "CustomUser")
    taken = set()
    for user in User.objects.filter(avatar_token__isnull=True).only("pk"):
        token = get_random_string(24)
        while token in taken:
            token = get_random_string(24)
        taken.add(token)
        User.objects.filter(pk=user.pk).update(avatar_token=token)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0015_xp_db_index")]

    operations = [
        migrations.AddField(
            model_name="customuser", name="avatar_token",
            field=models.CharField(max_length=32, null=True, editable=False),
        ),
        migrations.RunPython(fill_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="customuser", name="avatar_token",
            field=models.CharField(max_length=32, unique=True, default=accounts.models.new_avatar_token, editable=False),
        ),
    ]
