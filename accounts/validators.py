from django.core.exceptions import ValidationError
import re, datetime

ALLOWED_EXACT_DOMAINS = {"gmail.com", "hotmail.com", "outlook.com"}
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email_format(email):
    return bool(EMAIL_REGEX.match(email or ""))


def is_allowed_domain(email):
    if "@" not in email:
        return False
    domain = email.strip().lower().split("@")[-1]
    return domain in ALLOWED_EXACT_DOMAINS or domain.endswith(".edu")


def validate_cyberquest_email(email):
    if not is_valid_email_format(email):
        raise ValidationError("Please enter a valid email address (e.g. name@gmail.com).")
    if not is_allowed_domain(email):
        raise ValidationError("Only Gmail, Hotmail, Outlook, or .edu email addresses are allowed.")


def validate_special_character(password):
    """Used by AUTH_PASSWORD_VALIDATORS. Digits and letters alone are not enough."""
    if password and not re.search(r"[^A-Za-z0-9]", password):
        raise ValidationError("Password must include at least one special character.")


class SpecialCharacterValidator:
    """Django password validator: require a character that is not a letter or digit."""

    def validate(self, password, user=None):
        validate_special_character(password)

    def get_help_text(self):
        return "Your password must include at least one special character."


def validate_minimum_age(dob, minimum_age=13):
    """Shared by SignupForm and CompleteProfileForm so the age rule lives in one place."""
    if dob:
        today = datetime.date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < minimum_age:
            raise ValidationError(f"You must be at least {minimum_age} years old to register.")
