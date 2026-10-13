"""Re-encrypt stored TOTP secrets with the first key in FIELD_ENCRYPTION_KEYS.

Rotation: prepend a new key (NEW,OLD), deploy, run this command, then drop
OLD from the list. Legacy plaintext secrets are encrypted on the way.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.crypto import SecretDecryptionError, rotate_secret


class Command(BaseCommand):
    help = "Re-encrypt stored TOTP secrets with the current primary key."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count rows without writing.")

    def handle(self, *args, dry_run=False, **options):
        User = get_user_model()
        rows = User.objects.exclude(totp_secret="").only("pk", "totp_secret")
        done = failed = 0
        for user in rows.iterator():
            try:
                rotated = rotate_secret(user.totp_secret)
            except SecretDecryptionError:
                failed += 1
                self.stderr.write(f"User {user.pk}: secret could not be decrypted with any configured key.")
                continue
            if not dry_run:
                User.objects.filter(pk=user.pk).update(totp_secret=rotated)
            done += 1
        verb = "Would re-encrypt" if dry_run else "Re-encrypted"
        self.stdout.write(f"{verb} {done} secret(s).")
        if failed:
            raise CommandError(f"{failed} secret(s) could not be decrypted. Is an old key missing?")
