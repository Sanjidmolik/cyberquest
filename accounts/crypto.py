"""
Authenticated encryption for small secrets stored in the database.

TOTP secrets are encrypted with Fernet (AES-128-CBC + HMAC-SHA256). Keys come
from the FIELD_ENCRYPTION_KEYS environment variable, never from the database
or source control. The first key encrypts; every listed key can decrypt, so a
key can be rotated by prepending a new one and running
``manage.py rotate_field_encryption``.

When FIELD_ENCRYPTION_KEYS is empty, a key is derived from SECRET_KEY with
HKDF. That keeps local development working, but it ties stored secrets to
SECRET_KEY. Production should set a dedicated key (see the deploy check).
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings

PREFIX = "enc:v1:"


class SecretDecryptionError(Exception):
    """A stored secret could not be decrypted with any configured key."""


def _derived_key(secret: str | None = None) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"cyberquest.field-encryption",
        info=b"totp-secret",
    )
    return base64.urlsafe_b64encode(hkdf.derive((secret or settings.SECRET_KEY).encode("utf-8")))


def _configured_keys() -> list[bytes]:
    raw = getattr(settings, "FIELD_ENCRYPTION_KEYS", None) or []
    if isinstance(raw, str):
        raw = raw.split(",")
    return [key.strip().encode("ascii") for key in raw if key and key.strip()]


def using_dedicated_key() -> bool:
    return bool(_configured_keys())


def _fernet() -> MultiFernet:
    """The first key encrypts. Later keys only decrypt.

    SECRET_KEY-derived keys stay last in the list so secrets written before
    FIELD_ENCRYPTION_KEYS was set (or before SECRET_KEY was rotated into
    SECRET_KEY_FALLBACKS) remain readable until rotate_field_encryption runs.
    """
    derived = [_derived_key()] + [
        _derived_key(old) for old in getattr(settings, "SECRET_KEY_FALLBACKS", []) or []
    ]
    keys = _configured_keys() + derived
    return MultiFernet([Fernet(key) for key in keys])


def is_encrypted(value: str) -> bool:
    return bool(value) and value.startswith(PREFIX)


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    token = _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")
    return PREFIX + token


def decrypt_secret(stored: str) -> str:
    """Return the plaintext. Legacy unprefixed values are returned unchanged."""
    if not stored:
        return ""
    if not is_encrypted(stored):
        return stored
    try:
        return _fernet().decrypt(stored[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise SecretDecryptionError("Stored secret could not be decrypted.") from exc


def rotate_secret(stored: str) -> str:
    """Re-encrypt with the current primary key. Plaintext values become encrypted."""
    if not stored:
        return ""
    if not is_encrypted(stored):
        return encrypt_secret(stored)
    try:
        token = _fernet().rotate(stored[len(PREFIX):].encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError) as exc:
        raise SecretDecryptionError("Stored secret could not be decrypted.") from exc
    return PREFIX + token


def hash_verification_code(user_id, purpose: str, code: str) -> str:
    """Keyed hash for a short numeric code.

    A plain hash of a 6-digit code could be reversed by trying all 10^6
    values, so the HMAC key (SECRET_KEY) is what protects it at rest.
    """
    from django.utils.crypto import salted_hmac

    message = f"{user_id}:{purpose}:{(code or '').strip()}"
    return salted_hmac("accounts.VerificationCode", message, algorithm="sha256").hexdigest()
