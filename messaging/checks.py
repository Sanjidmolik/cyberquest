from cryptography.fernet import Fernet
from django.conf import settings
from django.core.checks import Error, register

GENERATE = 'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'


@register()
def message_key_configured(app_configs, **kwargs):
    keys = getattr(settings, "MESSAGE_ENCRYPTION_KEYS", [])
    if not keys:
        return [Error(
            "MESSAGE_ENCRYPTION_KEYS is not set, so messages can't be stored encrypted.",
            hint=f"Generate a key with {GENERATE}, put it in .env as MESSAGE_ENCRYPTION_KEYS=<key> "
                 "and back it up: losing it makes stored messages unreadable.",
            id="messaging.E001",
        )]
    errors = []
    for index, key in enumerate(keys, start=1):
        try:
            Fernet(key.encode() if isinstance(key, str) else key)
        except (ValueError, TypeError):
            errors.append(Error(
                f"MESSAGE_ENCRYPTION_KEYS entry {index} is not a valid Fernet key.",
                hint=f"Each comma-separated key must come from {GENERATE}.",
                id="messaging.E002",
            ))
    return errors
