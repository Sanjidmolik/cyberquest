"""Re-encrypt every stored message with the newest key in MESSAGE_ENCRYPTION_KEYS.

Rotation: put a new key FIRST in MESSAGE_ENCRYPTION_KEYS (keep the old ones after it),
deploy, run this command, then remove the old keys. Safe to run again.
"""

from django.core.management.base import BaseCommand

from messaging.crypto import rotate
from messaging.models import Message


class Command(BaseCommand):
    help = "Re-encrypt stored messages with the newest MESSAGE_ENCRYPTION_KEYS key."

    def handle(self, *args, **options):
        done = 0
        for message in Message.all_objects.exclude(body="").only("pk", "body").iterator(chunk_size=500):
            fresh = rotate(message.body)
            if fresh != message.body:
                Message.all_objects.filter(pk=message.pk).update(body=fresh)
                done += 1
        self.stdout.write(self.style.SUCCESS(f"Re-encrypted {done} messages."))
