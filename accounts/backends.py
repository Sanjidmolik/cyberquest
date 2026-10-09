"""
accounts/backends.py
-----------------------
A Django "authentication backend" is the piece that ACTUALLY checks
"does this email + password combination match a real account?"

We write our own so login is strictly by email (case-insensitive) and
so we can plug in extra checks later (e.g. "is account banned?") in
ONE place, without touching views.py or forms.py.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

UserModel = get_user_model()  # this will be accounts.CustomUser


class EmailAuthBackend(ModelBackend):
    # We inherit from ModelBackend (not BaseBackend) specifically because it
    # already provides `user_can_authenticate()`, which checks `is_active`
    # for us -- so inactive/banned accounts are automatically blocked.
    """Authenticate using email + password instead of username + password."""

    def authenticate(self, request, email=None, password=None, **kwargs):
        if email is None or password is None:
            return None

        try:
            user = UserModel.objects.get(email__iexact=email)
        except UserModel.DoesNotExist:
            # Important: don't reveal WHICH part was wrong (email vs password)
            # This is a security best-practice — avoid "user enumeration".
            return None

        if user.check_password(password) and self.user_can_authenticate(user) and user.email_verified:
            return user

        return None

    def get_user(self, user_id):
        """Required by Django: fetch a user by their primary key."""
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None
