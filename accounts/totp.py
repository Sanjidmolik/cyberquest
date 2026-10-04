"""Authenticator-app TOTP helpers. Secrets are not logged. Recovery codes are hashed."""

from __future__ import annotations

import secrets

import pyotp
from django.contrib.auth.hashers import check_password, make_password

from accounts.models import RecoveryCode


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="CyberQuest")


def verify_totp(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    return bool(pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1))


def issue_recovery_codes(user, count: int = 8) -> list[str]:
    user.recovery_codes.all().delete()
    raw = []
    rows = []
    for _ in range(count):
        code = secrets.token_hex(5)
        raw.append(code)
        rows.append(RecoveryCode(user=user, code_hash=make_password(code)))
    RecoveryCode.objects.bulk_create(rows)
    return raw


def consume_recovery_code(user, code: str) -> bool:
    submitted = (code or "").strip().lower()
    if not submitted:
        return False
    for row in user.recovery_codes.filter(used=False):
        if check_password(submitted, row.code_hash):
            row.used = True
            row.save(update_fields=["used"])
            return True
    return False
