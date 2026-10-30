"""Where view-once photos are stored: never under MEDIA_ROOT and never behind a URL.

Locally: PRIVATE_MEDIA_ROOT on disk (read on every access, so tests can point it elsewhere).
With MEDIA_STORAGE=r2: the private bucket (the default storage), under msg-photos/.
The files hold Fernet ciphertext only (messaging/photos.py), so a leaked file is unreadable.
"""

from django.conf import settings
from django.core.files.storage import FileSystemStorage, default_storage


class PrivateFileStorage(FileSystemStorage):
    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    def url(self, name):
        raise ValueError("Private files have no URL.")


_local = PrivateFileStorage()


def private_storage():
    return default_storage if getattr(settings, "MEDIA_STORAGE", "filesystem") == "r2" else _local
