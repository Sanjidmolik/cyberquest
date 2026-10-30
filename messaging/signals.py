"""Account deletion: the other person keeps the conversation, but the deleted user's messages
lose their text and show as "Deleted user" (the sender link is cleared by SET_NULL)."""

from django.conf import settings
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Message


@receiver(pre_delete, sender=settings.AUTH_USER_MODEL)
def remove_message_text(sender, instance, **kwargs):
    # Their unopened view-once photos are deleted outright.
    storage = Message._meta.get_field("photo").storage
    for name in Message.all_objects.filter(sender=instance).exclude(photo="").values_list("photo", flat=True):
        try:
            storage.delete(name)
        except Exception:  # noqa: BLE001 - the row is cleared either way
            pass
    Message.all_objects.filter(sender=instance).exclude(photo="").update(photo="")
    # all_objects: expired rows the cleanup hasn't reached yet lose their text too.
    Message.all_objects.filter(sender=instance).update(body="", removed=True)
