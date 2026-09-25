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


class ProfileSettingsForm(forms.ModelForm):
    """
    Lets a logged-in user edit their own personal profile fields.
    Intentionally excludes email (login identifier) and all system-
    controlled fields (xp, level, streaks, privileges, etc.).
    """
    MAX_IMAGE_BYTES = 5 * 1024 * 1024
    ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

    class Meta:
        model = UserModel
        fields = [
            "profile_picture",
            "full_name",
            "username",
            "date_of_birth",
            "cyber_class",
            "skill_level",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={
                "class": "cq-settings-input",
                "placeholder": "Your full name",
                "autocomplete": "name",
            }),
            "username": forms.TextInput(attrs={
                "class": "cq-settings-input",
                "placeholder": "Choose a unique username",
                "autocomplete": "username",
            }),
            "date_of_birth": forms.DateInput(attrs={
                "class": "cq-settings-input",
                "type": "date",
            }),
            "cyber_class": forms.Select(attrs={"class": "cq-settings-input"}),
            "skill_level": forms.Select(attrs={"class": "cq-settings-input"}),
            "profile_picture": forms.FileInput(attrs={
                "class": "cq-settings-file",
                "accept": "image/jpeg,image/png,image/webp,image/gif",
                "id": "id_profile_picture",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["profile_picture"].required = False
        self.fields["full_name"].required = False
        self.fields["username"].required = False
        self.fields["date_of_birth"].required = False

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            return None
        qs = UserModel.objects.filter(username__iexact=username)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("That username is already taken.")
        return username

    def clean_full_name(self):
        return (self.cleaned_data.get("full_name") or "").strip()

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")
        if dob:
            validate_minimum_age(dob)
        return dob

    def clean_profile_picture(self):
        picture = self.cleaned_data.get("profile_picture")
        if not picture:
            return picture

        # Skip re-validation when the field is unchanged (existing FileField value).
        if not hasattr(picture, "content_type") and not hasattr(picture, "read"):
            return picture
        if getattr(self.instance, "profile_picture", None) and picture == self.instance.profile_picture:
            return picture

        if getattr(picture, "size", 0) > self.MAX_IMAGE_BYTES:
            raise ValidationError("Image must be smaller than 5MB.")

        content_type = getattr(picture, "content_type", None)
        if content_type and not content_type.startswith("image/"):
            raise ValidationError("Please upload an image file (JPG, PNG, WEBP, or GIF).")

        try:
            from PIL import Image

            picture.seek(0)
            with Image.open(picture) as img:
                img.verify()
            picture.seek(0)
            with Image.open(picture) as img:
                img.load()
                if img.format not in self.ALLOWED_IMAGE_FORMATS:
                    raise ValidationError("Please upload a JPG, PNG, WEBP, or GIF image.")
            picture.seek(0)
        except ValidationError:
            raise
        except Exception:
            raise ValidationError("The uploaded file is not a valid image.")

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
