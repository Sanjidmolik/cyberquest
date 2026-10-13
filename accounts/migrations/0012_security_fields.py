from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_shared_cache_table"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="security_stamp",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="customuser",
            name="totp_last_used_step",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="customuser",
            name="totp_secret",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="verificationcode",
            name="code_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AlterField(
            model_name="verificationcode",
            name="code",
            field=models.CharField(blank=True, default="", max_length=6),
        ),
        migrations.AddIndex(
            model_name="verificationcode",
            index=models.Index(fields=["user", "purpose", "created_at"], name="accounts_vc_lookup_idx"),
        ),
    ]
