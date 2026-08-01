"""
accounts/forms.py
-------------------
Defines the LOGIN FORM shown on the login page.

This file's ONLY job is: define the fields, and plug in email validation
from validators.py. It does NOT do authentication itself — that happens
in views.py + backends.py. Keeping this separation means:
  - forms.py  = what fields exist + basic validation
  - backends.py = HOW a user is actually authenticated (password check)
  - views.py  = what happens on GET/POST requests
"""

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .validators import validate_cyberquest_email

UserModel = get_user_model()


class SignupForm(forms.Form):
    """
    Registration form. Reuses the SAME email validator as login, so the
    gmail/hotmail/outlook/.edu rule is enforced in exactly one place
    (validators.py) instead of being duplicated here.

    Field list matches the project's signup spec:
    Username, Email, Password, Date of Birth, Cyber Class/Role,
    Skill Level, Ethical Agreement.
    """

    username = forms.CharField(
        label="Username",
        max_length=50,
        widget=forms.TextInput(attrs={
            "class": "cq-input",
            "placeholder": "your_public_handle",
        }),
        help_text="This is your public identity on leaderboards.",
    )

    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={
            "class": "cq-input",
            "placeholder": "you@gmail.com",
        }),
    )

    password = forms.CharField(
        label="Password",
        min_length=8,
        widget=forms.PasswordInput(attrs={
            "class": "cq-input",
            "placeholder": "At least 8 characters",
        }),
    )

    confirm_password = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={
            "class": "cq-input",
            "placeholder": "Re-enter password",
        }),
    )

    date_of_birth = forms.DateField(
        label="Date of birth",
        widget=forms.DateInput(attrs={
            "class": "cq-input",
            "type": "date",   # renders a native date picker in the browser
        }),
    )

    cyber_class = forms.ChoiceField(
        label="Cyber Class / Role",
        choices=UserModel.CYBER_CLASS_CHOICES,
        widget=forms.RadioSelect,  # displayed as selectable "cards" via CSS
    )

    skill_level = forms.ChoiceField(
        label="Skill Level",
        choices=UserModel.SKILL_LEVEL_CHOICES,
        widget=forms.RadioSelect,
    )

    ethical_agreement = forms.BooleanField(
        label="I agree to use CyberQuest's tools and techniques ethically and legally.",
        required=True,  # must be checked -- Django rejects the form otherwise
        error_messages={"required": "You must accept the ethical use agreement to register."},
    )

    def clean_username(self):
        """Enforce that the public username is unique too (not just email)."""
        username = self.cleaned_data.get("username", "").strip()
        if UserModel.objects.filter(username__iexact=username).exists():
            raise ValidationError("That username is already taken.")
        return username

    def clean_date_of_birth(self):
        """Basic legal-compliance check: require the trainee to be at least 13."""
        import datetime
        dob = self.cleaned_data.get("date_of_birth")
        if dob:
            today = datetime.date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < 13:
                raise ValidationError("You must be at least 13 years old to register.")
        return dob

    def clean_email(self):
        """Run our domain rule, PLUS check the email isn't already taken."""
        email = self.cleaned_data.get("email", "")
        validate_cyberquest_email(email)  # gmail/hotmail/outlook/.edu only

        if UserModel.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")

        return email

    def clean(self):
        """
        clean() (no field name) runs AFTER all individual fields are clean --
        used here to compare two fields against each other (password match).
        """
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")

        return cleaned_data


class LoginForm(forms.Form):
    """Simple email + password login form (not tied to a model)."""

    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={
            "class": "cq-input",
            "placeholder": "you@gmail.com",
            "autofocus": True,
        }),
    )

    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "class": "cq-input",
            "placeholder": "••••••••",
        }),
    )

    def clean_email(self):
        """
        Django automatically calls clean_<fieldname>() for each field.
        This runs OUR custom domain-check on top of Django's built-in
        EmailField format check.
        """
        email = self.cleaned_data.get("email", "")
        validate_cyberquest_email(email)  # raises ValidationError if invalid
        return email
