"""Message bodies at rest: Fernet (AES-128-CBC + HMAC-SHA256) with MultiFernet for rotation.

Keys come from MESSAGE_ENCRYPTION_KEYS (newest first), never from the database. The server
can decrypt, so this protects stored data (database dumps, backups); it is not end-to-end
encryption. Without a key the app refuses to start (messaging/checks.py).
"""

from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@lru_cache(maxsize=4)
def _fernet(keys):
    if not keys:
        raise ImproperlyConfigured("MESSAGE_ENCRYPTION_KEYS is not set; messaging cannot store messages.")
    return MultiFernet([Fernet(key.encode() if isinstance(key, str) else key) for key in keys])


def _current():
    return _fernet(tuple(settings.MESSAGE_ENCRYPTION_KEYS))


def encrypt(text):
    return _current().encrypt(text.encode("utf-8")).decode("ascii")


def decrypt(token):
    return _current().decrypt(token.encode("ascii")).decode("utf-8")


def rotate(token):
    """Re-encrypt with the newest key (after a new key was put first)."""
    return _current().rotate(token.encode("ascii")).decode("ascii")
