"""
accounts/codes.py
--------------------
ONE JOB: create and validate VerificationCode records. Views call these
functions instead of building/checking codes inline, so the "how long is
a code valid" and "how is it generated" rules live in exactly one place.
"""

import secrets
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from .models import VerificationCode

CODE_VALID_MINUTES = 10
MAX_ATTEMPTS = 5
GENERATE_COOLDOWN_SECONDS = 45


def generate_code(user, purpose: str) -> VerificationCode:
    """
    Create a new cryptographically random 6-digit code for this user + purpose.
    Previous unused codes for the same purpose are invalidated. A short cooldown
    limits resend spam without requiring a schema change.
    """
    cooldown_key = f"vc_gen:{user.pk}:{purpose}"
    if cache.get(cooldown_key):
        latest = (
            VerificationCode.objects
            .filter(user=user, purpose=purpose, is_used=False)
            .order_by("-created_at")
            .first()
        )
        if latest is not None and latest.is_valid():
            return latest

    VerificationCode.objects.filter(
        user=user, purpose=purpose, is_used=False
    ).update(is_used=True)

    # Keyed by user+purpose so TestCase DB rollbacks cannot reuse a stale
    # per-row attempt counter from LocMemCache.
    cache.delete(f"vc_attempts:{user.pk}:{purpose}")

    code_value = f"{secrets.randbelow(1_000_000):06d}"
    record = VerificationCode.objects.create(
        user=user,
        code=code_value,
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=CODE_VALID_MINUTES),
    )
    cache.set(cooldown_key, 1, GENERATE_COOLDOWN_SECONDS)
    return record


def check_code(user, purpose: str, submitted_code: str) -> bool:
    """
    Check the submitted code against the user's MOST RECENT unused code
    for this purpose. Expiry, single-use, and attempt limiting are enforced
    here (attempt counts live in cache — no migration required).
    """
    latest_code = (
        VerificationCode.objects
        .filter(user=user, purpose=purpose)
        .order_by("-created_at")
        .first()
    )

    if latest_code is None or not latest_code.is_valid():
        return False

    attempt_key = f"vc_attempts:{user.pk}:{purpose}"
    attempts = int(cache.get(attempt_key) or 0)
    if attempts >= MAX_ATTEMPTS:
        latest_code.is_used = True
        latest_code.save(update_fields=["is_used"])
        return False

    submitted = (submitted_code or "").strip()
    expected = latest_code.code
    if len(submitted) != len(expected) or not secrets.compare_digest(submitted, expected):
        attempts += 1
        cache.set(attempt_key, attempts, CODE_VALID_MINUTES * 60)
        if attempts >= MAX_ATTEMPTS:
            latest_code.is_used = True
            latest_code.save(update_fields=["is_used"])
        return False

    latest_code.is_used = True
    latest_code.save(update_fields=["is_used"])
    cache.delete(attempt_key)
    return True
