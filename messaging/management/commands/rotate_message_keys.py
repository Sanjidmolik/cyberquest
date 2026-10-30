"""Re-encrypt every stored message with the newest key in MESSAGE_ENCRYPTION_KEYS.

Rotation: put a new key FIRST in MESSAGE_ENCRYPTION_KEYS (keep the old ones after it),
deploy, run this command, then remove the old keys. Safe to run again.
"""

from django.core.management.base import BaseCommand

from django.core.files.base import ContentFile

from messaging.crypto import rotate, rotate_bytes
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
        files = 0
        from moderation.models import Report
        for model, manager, column in ((Message, Message.all_objects, "photo"), (Message, Message.all_objects, "report_copy"),
                                       (Report, Report.objects, "photo")):
            field = model._meta.get_field(column)
            for pk, name in manager.exclude(**{column: ""}).values_list("pk", column).iterator(chunk_size=200):
                with field.storage.open(name, "rb") as handle:
                    token = handle.read()
                fresh = rotate_bytes(token)
                if fresh != token:
                    field.storage.delete(name)
                    field.storage.save(name, ContentFile(fresh))
                    files += 1
        self.stdout.write(self.style.SUCCESS(f"Re-encrypted {done} messages and {files} photo files."))
