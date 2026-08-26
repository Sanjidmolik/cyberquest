"""
accounts/emails.py
---------------------
ONE JOB: send CyberQuest's transactional emails. Keeping every email's
subject/body in one file means the wording is easy to find and update
without hunting through views.py.

In development, EMAIL_BACKEND is set to Django's console backend (see
settings.py), so these emails print to your terminal instead of actually
sending -- no real email account is needed to test any of this.
"""

from django.core.mail import send_mail
from django.conf import settings


def send_welcome_email(user):
    """Sent once, right after a successful signup."""
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
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)


def send_login_2fa_email(user, code):
    """Sent every time a user logs in, as the second authentication factor."""
    subject = "Your CyberQuest verification code"
    message = (
        f"Hi {user.display_name()},\n\n"
        f"Your CyberQuest login verification code is: {code}\n\n"
        "This code expires in 10 minutes. If you didn't try to log in, "
        "you can safely ignore this email.\n\n"
        "-- The CyberQuest Team"
    )
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)


def send_password_reset_email(user, code):
    """Sent when a user requests a password reset."""
    subject = "Reset your CyberQuest password"
    message = (
        f"Hi {user.display_name()},\n\n"
        f"Your CyberQuest password reset code is: {code}\n\n"
        "Enter this code on the password reset page to choose a new password. "
        "This code expires in 10 minutes. If you didn't request this, you can "
        "safely ignore this email -- your password will not be changed.\n\n"
        "-- The CyberQuest Team"
    )
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
