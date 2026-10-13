"""Encrypt existing TOTP secrets and hash existing verification codes.

Idempotent: already-encrypted secrets and already-hashed codes are skipped.
No rows are deleted. Used or expired codes only lose their plaintext.
"""

from django.db import migrations


def encrypt_totp_secrets(User):
    from accounts.crypto import encrypt_secret, is_encrypted

    for user in User.objects.exclude(totp_secret="").only("pk", "totp_secret").iterator():
        if is_encrypted(user.totp_secret):
            continue
        User.objects.filter(pk=user.pk).update(totp_secret=encrypt_secret(user.totp_secret))


def hash_verification_codes(Code):
    from accounts.crypto import hash_verification_code

    for row in Code.objects.exclude(code="").only("pk", "user_id", "purpose", "code").iterator():
        Code.objects.filter(pk=row.pk).update(
            code_hash=hash_verification_code(row.user_id, row.purpose, row.code),
            code="",
        )


def forwards(apps, schema_editor):
    encrypt_totp_secrets(apps.get_model("accounts", "CustomUser"))
    hash_verification_codes(apps.get_model("accounts", "VerificationCode"))


def backwards(apps, schema_editor):
    # Secrets are decrypted so an older release can read them. Codes cannot be
    # un-hashed; they expire within minutes, so users simply request new ones.
    from accounts.crypto import decrypt_secret, is_encrypted

    User = apps.get_model("accounts", "CustomUser")
    for user in User.objects.exclude(totp_secret="").only("pk", "totp_secret").iterator():
        if is_encrypted(user.totp_secret):
            User.objects.filter(pk=user.pk).update(totp_secret=decrypt_secret(user.totp_secret))


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_security_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
