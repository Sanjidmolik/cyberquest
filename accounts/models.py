"""
accounts/models.py
-------------------
Defines the CUSTOM USER MODEL for CyberQuest.

WHY a custom model?
Django's built-in User model logs in with a "username". We want users to log
in with EMAIL ONLY, so we extend Django's base classes and remove the
username requirement entirely.

This file only defines WHAT a user looks like (the database table).
The RULES for which email domains are allowed live in accounts/forms.py
and accounts/validators.py — kept separate on purpose.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class CustomUserManager(BaseUserManager):
    """
    A 'manager' is the class Django uses to CREATE users
    (e.g. CustomUser.objects.create_user(...)).

    We override it because the default manager expects a username field,
    which we no longer have.
    """

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular user with the given email and password."""
        if not email:
            raise ValueError("Users must have an email address")

        email = self.normalize_email(email)  # lowercases the domain part
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # hashes the password — never store plain text
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save an admin (superuser) account."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """
    Our custom user table.

    AbstractBaseUser  -> gives us password hashing, last_login, etc.
    PermissionsMixin  -> gives us is_staff/is_superuser/permissions (for /admin/)
    """

    # ---- Core identity fields ----
    email = models.EmailField(unique=True)          # login identifier (private)
    username = models.CharField(                     # public identity, e.g. on leaderboards
        max_length=50, unique=True, blank=True, null=True
    )
    full_name = models.CharField(max_length=150, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)

    # ---- Cyber Class / Role: sets the trainee's initial learning path ----
    CYBER_CLASS_CHOICES = [
        ("ethical_hacker", "Ethical Hacker"),
        ("blue_team", "Defender / Blue Team"),
        ("osint", "OSINT Investigator"),
        ("malware_analyst", "Malware Analyst"),
        ("general", "General Recruit"),
    ]
    cyber_class = models.CharField(
        max_length=30, choices=CYBER_CLASS_CHOICES, default="general"
    )

    # ---- Skill level: calibrates challenge difficulty ----
    SKILL_LEVEL_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]
    skill_level = models.CharField(
        max_length=20, choices=SKILL_LEVEL_CHOICES, default="beginner"
    )

    # ---- Legal / safety compliance ----
    ethical_agreement = models.BooleanField(default=False)

    # DEPRECATED: course completion is now tracked per-course via
    # courses.models.CourseProgress (a user must complete ALL published
    # courses). This field is left in place for backward compatibility
    # but is no longer read anywhere in the codebase.
    course_intro_completed = models.BooleanField(default=False)

    # ---- Gamification (used by the dashboard) ----
    xp = models.PositiveIntegerField(default=0)
    level = models.PositiveIntegerField(default=1)

    is_active = models.BooleanField(default=True)    # can this account log in?
    is_staff = models.BooleanField(default=False)    # can access /admin/?

    date_joined = models.DateTimeField(auto_now_add=True)

    objects = CustomUserManager()  # tell Django to use OUR manager above

    USERNAME_FIELD = 'email'       # <-- THIS makes email the login field
    REQUIRED_FIELDS = []           # no extra fields required at shell-level createsuperuser

    def __str__(self):
        # what shows up in Django admin / shell when you print a user
        return self.email

    def display_name(self):
        """Prefer the public username; fall back to full name, then email prefix."""
        return self.username or self.full_name or self.email.split("@")[0]
