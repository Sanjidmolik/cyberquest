from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_features_loader_visits_2fa_analytics"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="email_2fa_enabled",
            field=models.BooleanField(
                default=False,
                help_text="When on, password login emails a 6-digit code. Off unless the user turns it on.",
            ),
        ),
    ]
