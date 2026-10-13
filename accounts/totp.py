"""Authenticator-app TOTP helpers.

Secrets are encrypted at rest (see accounts.crypto) and never logged.
Recovery codes are hashed. A code is accepted at most once: the matched
time step is stored and later codes must use a newer step.
"""

from __future__ import annotations

import secrets

import pyotp
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from accounts.models import CustomUser, RecoveryCode

VALID_WINDOW = 1
USER_FAILURE_LIMIT = 10
USER_FAILURE_WINDOW_SECONDS = 900


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="CyberQuest")


def _normalize(code: str) -> str:
    return (code or "").strip().replace(" ", "")


def matching_step(secret: str, code: str, *, for_time=None) -> int | None:
    """Return the time step the code belongs to, or None when it does not match."""
    code = _normalize(code)
    if not secret or not code or not code.isdigit():
        return None
    totp = pyotp.TOTP(secret)
    now = for_time or timezone.now()
    current = totp.timecode(now)
    for offset in range(-VALID_WINDOW, VALID_WINDOW + 1):
        step = current + offset
        if secrets.compare_digest(totp.generate_otp(step), code):
            return step
    return None


def verify_totp(secret: str, code: str) -> bool:
    """Stateless check, used only while enrolling a secret that is not saved yet."""
    return matching_step(secret, code) is not None


def verify_user_totp(user, code: str) -> bool:
    """Check a code against the user's stored secret and burn its time step.

    The conditional UPDATE makes acceptance atomic, so a replayed or
    concurrently submitted code for the same step is refused.
    """
    if not user.totp_enabled or not user.totp_secret:
        return False
    step = matching_step(user.get_totp_secret(), code)
    if step is None:
        return False
    claimed = CustomUser.objects.filter(pk=user.pk).filter(
        Q(totp_last_used_step__isnull=True) | Q(totp_last_used_step__lt=step)
    ).update(totp_last_used_step=step)
    if claimed:
        user.totp_last_used_step = step
    return bool(claimed)


def _failure_key(user) -> str:
    return f"totp_fail:{user.pk}"


def user_locked(user) -> bool:
    """Account-level throttle. The session counter alone resets with a new session."""
    return int(cache.get(_failure_key(user)) or 0) >= USER_FAILURE_LIMIT


def register_user_failure(user) -> None:
    key = _failure_key(user)
    if cache.add(key, 1, USER_FAILURE_WINDOW_SECONDS):
        return
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, USER_FAILURE_WINDOW_SECONDS)


def clear_user_failures(user) -> None:
    cache.delete(_failure_key(user))


def _format_recovery_code(raw: str) -> str:
    """Return a 32-char hex code grouped as XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX."""
    return "-".join(raw[i:i+8] for i in range(0, 32, 8))


def _normalize_recovery_code(code: str) -> str:
    """Strip hyphens, spaces, and lowercase so both formatted and raw input match."""
    return (code or "").strip().replace("-", "").replace(" ", "").lower()


def issue_recovery_codes(user, count: int = 8) -> list[str]:
    user.recovery_codes.all().delete()
    raw = []
    rows = []
    for _ in range(count):
        code = secrets.token_hex(16)  # 128-bit entropy (NIST SP 800-63B §5.1.2 min is 112 bits)
        raw.append(_format_recovery_code(code))
        rows.append(RecoveryCode(user=user, code_hash=make_password(code)))
    RecoveryCode.objects.bulk_create(rows)
    return raw


def consume_recovery_code(user, code: str) -> bool:
    submitted = _normalize_recovery_code(code)
    if not submitted:
        return False
    for row in user.recovery_codes.filter(used=False):
        if check_password(submitted, row.code_hash):
            return bool(RecoveryCode.objects.filter(pk=row.pk, used=False).update(used=True))
    return False
