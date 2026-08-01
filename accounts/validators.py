"""
accounts/validators.py
------------------------
ONE JOB ONLY: decide whether an email address is allowed to register/login.

Kept in its own file (separate from forms.py and views.py) so that if you
ever want to change the allowed domain list, you edit ONLY this file and
nothing else in the project is affected.
"""

from django.core.exceptions import ValidationError
import re

# The only domains CyberQuest currently accepts.
# ".edu" is handled separately below since it's a suffix, not one fixed domain.
ALLOWED_EXACT_DOMAINS = {
    "gmail.com",
    "hotmail.com",
    "outlook.com",
}

# A basic but solid email format check (structure: something@something.tld)
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email_format(email: str) -> bool:
    """Check the email LOOKS like a real email address (basic structural check)."""
    return bool(EMAIL_REGEX.match(email or ""))


def is_allowed_domain(email: str) -> bool:
    """
    Check the email's domain is one of our allowed providers:
    gmail.com, hotmail.com, outlook.com, or anything ending in .edu
    (e.g. student.university.edu, mit.edu, etc.)
    """
    if "@" not in email:
        return False

    domain = email.strip().lower().split("@")[-1]

    if domain in ALLOWED_EXACT_DOMAINS:
        return True

    if domain.endswith(".edu"):
        return True

    return False


def validate_cyberquest_email(email: str) -> None:
    """
    Main entry point used by forms.py.
    Raises a ValidationError with a clear message if anything is wrong.
    Raises NOTHING (returns silently) if the email is OK.
    """
    if not is_valid_email_format(email):
        raise ValidationError("Please enter a valid email address (e.g. name@gmail.com).")

    if not is_allowed_domain(email):
        raise ValidationError(
            "Only Gmail, Hotmail, Outlook, or .edu email addresses are allowed."
        )
