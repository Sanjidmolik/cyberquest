from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .validators import validate_cyberquest_email, validate_minimum_age

UserModel = get_user_model()


class SignupForm(forms.Form):
    username = forms.CharField(label="Username", max_length=50,
        widget=forms.TextInput(attrs={"class": "cq-input"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "cq-input"}))
    password = forms.CharField(min_length=8, widget=forms.PasswordInput(attrs={"class": "cq-input"}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "cq-input"}))
    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={"class": "cq-input", "type": "date"}))
    cyber_class = forms.ChoiceField(choices=UserModel.CYBER_CLASS_CHOICES, widget=forms.RadioSelect)
    skill_level = forms.ChoiceField(choices=UserModel.SKILL_LEVEL_CHOICES, widget=forms.RadioSelect)
    ethical_agreement = forms.BooleanField(
        label="I agree to use CyberQuest's tools and techniques ethically and legally.",
        required=True,
        error_messages={"required": "You must accept the ethical use agreement to register."})

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if UserModel.objects.filter(username__iexact=username).exists():
            raise ValidationError("That username is already taken.")
        return username

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")
        validate_minimum_age(dob)
        return dob

    def clean_email(self):
        email = self.cleaned_data.get("email", "")
        validate_cyberquest_email(email)
        if UserModel.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password") != cleaned_data.get("confirm_password"):
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned_data


class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "cq-input", "autofocus": True}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "cq-input"}))

    def clean_email(self):
        email = self.cleaned_data.get("email", "")
        validate_cyberquest_email(email)
        return email


class ProfilePictureForm(forms.Form):
    profile_picture = forms.ImageField(required=True)

    def clean_profile_picture(self):
        picture = self.cleaned_data["profile_picture"]
        if picture.size > 5 * 1024 * 1024:
            raise ValidationError("Image must be smaller than 5MB.")
        return picture


class CompleteProfileForm(forms.Form):
    """
    Shown once, only to accounts created via Google Sign-In (their email
    is already verified by Google, but we still need CyberQuest-specific
    fields the OAuth flow doesn't provide: DOB, class, skill level, and
    explicit acceptance of the ethical use agreement).
    """
    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={"class": "cq-input", "type": "date"}))
    cyber_class = forms.ChoiceField(choices=UserModel.CYBER_CLASS_CHOICES, widget=forms.RadioSelect)
    skill_level = forms.ChoiceField(choices=UserModel.SKILL_LEVEL_CHOICES, widget=forms.RadioSelect)
    ethical_agreement = forms.BooleanField(
        label="I agree to use CyberQuest's tools and techniques ethically and legally.",
        required=True,
        error_messages={"required": "You must accept the ethical use agreement to continue."})

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")
        validate_minimum_age(dob)
        return dob
