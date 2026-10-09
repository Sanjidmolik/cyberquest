"""
accounts/emails.py
---------------------
ONE JOB: send CyberQuest's transactional emails. Keeping every email's
subject/body in one file means the wording is easy to find and update
without hunting through views.py.

Delivery failures return False instead of raising, and fail_silently stays
False so a backend error is not reported as a successful send.
"""

import logging

from django.core.mail import send_mail
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


def _deliver(subject, message, recipient) -> bool:
    """
    Hand one message to the email backend.
    Returns False when the backend raises or accepts nothing. Never swallows
    a failure by pretending the message was sent.
    """
    recipient = (recipient or "").strip()
    if not recipient:
        return False
    sender = settings.DEFAULT_FROM_EMAIL
    try:
        accepted = send_mail(subject, message, sender, [recipient], fail_silently=False)
    except (TimeoutError, OSError) as exc:
        logger.warning("SMTP delivery failed: %s", type(exc).__name__)
        return False
    except Exception:
        logger.warning("Email delivery failed")
        return False
    return bool(accepted)


def send_welcome_email(user):
    """
    Sent once, right after a successful signup.
    A delivery failure must not raise: the account is already created.
    Returns False when the welcome message was not accepted.
    """
    subject = "Welcome to CyberQuest!"
    message = (
        f"Hi {user.display_name()},\n\n"
        "Welcome to CyberQuest -- your cybersecurity training simulator!\n\n"
        "Your account has been created successfully. Log in, complete the "
        "training courses, and start earning XP by playing the security "
        "simulation games.\n\n"
        "Stay safe out there.\n"
        "-- The CyberQuest Team"
    )
    return _deliver(subject, message, user.email)


def send_signup_verification_email(user, code):
    """
    Sent after a password signup, before the account can sign in.
    Returns False when the message was not handed to the email backend.
    """
    subject = "Confirm your CyberQuest email"
    message = (
        f"Hi {user.display_name()},\n\n"
        f"Your CyberQuest email confirmation code is: {code}\n\n"
        "Enter this code to finish creating your account. "
        "This code expires in 10 minutes. If you didn't sign up, you can ignore this email.\n\n"
        "-- The CyberQuest Team"
    )
    return _deliver(subject, message, user.email)


def send_login_2fa_email(user, code):
    """
    Sent on password login only when the user has turned email codes on.
    Returns False when the message was not handed to the email backend.
    """
    subject = "Your CyberQuest verification code"
    message = (
        f"Hi {user.display_name()},\n\n"
        f"Your CyberQuest login verification code is: {code}\n\n"
        "This code expires in 10 minutes. If you didn't try to log in, "
        "you can safely ignore this email.\n\n"
        "-- The CyberQuest Team"
    )
    return _deliver(subject, message, user.email)


def send_password_reset_email(user, code):
    """
    Sent when a user requests a password reset.
    Returns False when the message was not handed to the email backend.
    """
    subject = "Reset your CyberQuest password"
    message = (
        f"Hi {user.display_name()},\n\n"
        f"Your CyberQuest password reset code is: {code}\n\n"
        "Enter this code on the password reset page to choose a new password. "
        "This code expires in 10 minutes. If you didn't request this, you can "
        "safely ignore this email -- your password will not be changed.\n\n"
        "-- The CyberQuest Team"
    )
    return _deliver(subject, message, user.email)


def send_account_status_email(user, active):
    """
    Tell a student their sign-in was suspended or restored.
    Returns True only after send_mail succeeds. Never includes SMTP details.
    """
    if user.is_staff or user.is_superuser:
        return False
    recipient = (user.email or "").strip()
    sender = (settings.DEFAULT_FROM_EMAIL or "").strip()
    try:
        validate_email(recipient)
    except ValidationError:
        return False
    if not sender:
        return False
    name = user.display_name()
    if active:
        subject = "Your CyberQuest account is active again"
        body = (
            f"Hello {name},\n\n"
            "An administrator restored your CyberQuest account. You can sign in again.\n\n"
            "-- The CyberQuest Team"
        )
    else:
        subject = "Your CyberQuest account is suspended"
        body = (
            f"Hello {name},\n\n"
            "An administrator suspended your CyberQuest account. "
            "You cannot sign in until it is restored.\n\n"
            "-- The CyberQuest Team"
        )
    try:
        send_mail(subject, body, sender, [recipient], fail_silently=False)
    except Exception:
        return False
    return True
