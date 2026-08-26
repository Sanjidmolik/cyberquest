"""
accounts/codes.py
--------------------
ONE JOB: create and validate VerificationCode records. Views call these
functions instead of building/checking codes inline, so the "how long is
a code valid" and "how is it generated" rules live in exactly one place.
"""

import random
from django.utils import timezone
from datetime import timedelta

from .models import VerificationCode

CODE_VALID_MINUTES = 10


def generate_code(user, purpose: str) -> VerificationCode:
    """Create a new 6-digit code for this user + purpose, valid for 10 minutes."""
    code_value = f"{random.randint(0, 999999):06d}"  # always 6 digits, zero-padded
    return VerificationCode.objects.create(
        user=user,
        code=code_value,
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=CODE_VALID_MINUTES),
    )


def check_code(user, purpose: str, submitted_code: str) -> bool:
    """
    Check the submitted code against the user's MOST RECENT unused code
    for this purpose. If correct, marks it used (so it can't be replayed).
    Returns True/False.
    """
    latest_code = (
        VerificationCode.objects
        .filter(user=user, purpose=purpose)
        .order_by("-created_at")
        .first()
    )

    if latest_code is None or not latest_code.is_valid():
        return False

    if latest_code.code != submitted_code.strip():
        return False

    latest_code.is_used = True
    latest_code.save(update_fields=["is_used"])
    return True
