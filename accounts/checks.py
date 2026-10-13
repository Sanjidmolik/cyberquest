"""Deployment checks for secrets that protect stored authentication data."""

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def field_encryption_key_check(app_configs, **kwargs):
    from cryptography.fernet import Fernet

    from .crypto import _configured_keys

    keys = _configured_keys()
    if not keys:
        return [Warning(
            "FIELD_ENCRYPTION_KEYS is not set. TOTP secrets are encrypted with a key "
            "derived from SECRET_KEY, so rotating SECRET_KEY would make them unreadable.",
            hint="Generate one with: python -c \"from cryptography.fernet import Fernet; "
                 "print(Fernet.generate_key().decode())\" and set it in the environment.",
            id="accounts.W001",
        )]
    for key in keys:
        try:
            Fernet(key)
        except (ValueError, TypeError):
            return [Warning(
                "FIELD_ENCRYPTION_KEYS contains a value that is not a valid Fernet key.",
                id="accounts.W002",
            )]
    return []
