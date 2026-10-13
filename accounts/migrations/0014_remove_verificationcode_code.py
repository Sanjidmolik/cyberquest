from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0013_protect_stored_secrets"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="verificationcode",
            name="code",
        ),
    ]
