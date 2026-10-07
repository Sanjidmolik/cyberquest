from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=50, unique=True, blank=True, null=True)
    full_name = models.CharField(max_length=150, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)

    CYBER_CLASS_CHOICES = [
        ("ethical_hacker", "Ethical Hacker"), ("blue_team", "Defender / Blue Team"),
        ("osint", "OSINT Investigator"), ("malware_analyst", "Malware Analyst"),
        ("general", "General Recruit"),
    ]
    cyber_class = models.CharField(max_length=30, choices=CYBER_CLASS_CHOICES, default="general")

    SKILL_LEVEL_CHOICES = [("beginner", "Beginner"), ("intermediate", "Intermediate"), ("advanced", "Advanced")]
    skill_level = models.CharField(max_length=20, choices=SKILL_LEVEL_CHOICES, default="beginner")

    ethical_agreement = models.BooleanField(default=False)
    course_intro_completed = models.BooleanField(default=False)
    google_linked = models.BooleanField(
        default=False,
        help_text="True if this account was created via 'Sign in with Google' (no local password set).",
    )
    profile_picture = models.ImageField(upload_to="profile_pictures/", blank=True, null=True)

    xp = models.PositiveIntegerField(default=0)
    level = models.PositiveIntegerField(default=1)

    # ---- Real login-streak tracking (powers the dashboard's Day Streak) ----
    current_streak = models.PositiveIntegerField(default=0)
    longest_streak = models.PositiveIntegerField(default=0)
    last_active_date = models.DateField(blank=True, null=True)
    totp_enabled = models.BooleanField(default=False)
    totp_secret = models.CharField(max_length=64, blank=True, default="")
    email_2fa_enabled = models.BooleanField(
        default=False,
        help_text="When on, password login emails a 6-digit code. Off unless the user turns it on.",
    )

    def record_daily_activity(self):
        """
        Call this once per login. Increments the streak if the user was
        also active yesterday; resets to 1 if they missed a day; does
        nothing if they've already been recorded today (so refreshing
        the page repeatedly doesn't inflate the streak).
        """
        from django.utils import timezone
        today = timezone.localdate()

        if self.last_active_date == today:
            return  # already counted today

        if self.last_active_date == today - timezone.timedelta(days=1):
            self.current_streak += 1
        else:
            self.current_streak = 1  # missed a day (or first-ever activity)

        self.longest_streak = max(self.longest_streak, self.current_streak)
        self.last_active_date = today
        self.save(update_fields=["current_streak", "longest_streak", "last_active_date"])
        UserActivityDay.objects.get_or_create(user=self, day=today)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = CustomUserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    def display_name(self):
        return self.username or self.full_name or self.email.split("@")[0]


class VerificationCode(models.Model):
    PURPOSE_CHOICES = [("login_2fa", "Login Verification"), ("password_reset", "Password Reset")]
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name="verification_codes")
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        from django.utils import timezone
        return (not self.is_used) and timezone.now() < self.expires_at


class UserActivityDay(models.Model):
    """One row per user per calendar day they authenticate. Used for active-user analytics."""

    user = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.CASCADE,
        related_name="activity_days",
    )
    day = models.DateField(db_index=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "day"], name="uniq_user_activity_day"),
        ]
        indexes = [models.Index(fields=["day", "user"])]

    def __str__(self):
        return f"{self.user_id} @ {self.day}"


class RecoveryCode(models.Model):
    """Hashed one-time recovery codes for authenticator 2FA. Never store the raw code."""

    user = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.CASCADE,
        related_name="recovery_codes",
    )
    code_hash = models.CharField(max_length=128)
    used = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["user", "used"])]
