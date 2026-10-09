"""
accounts/views.py
--------------------
Google Sign-In flow, added alongside the existing email/password + 2FA
flow:

  google_login_start()    -- redirects the user to Google's consent screen
  google_login_callback() -- Google redirects back here with a `code`;
                              we exchange it for the user's verified email,
                              then log them in (creating an account on
                              first sign-in).

DESIGN DECISION: Google Sign-In does NOT also require our own 6-digit
2FA code. Google's own sign-in already typically enforces its own
2FA/verification on the user's Google account -- requiring a SECOND,
separate 2FA step here would be redundant friction, not extra security.
"""

import secrets
from django.contrib.auth import login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.files.base import ContentFile
import requests

from cyberquest.ratelimit import rate_limit

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .forms import AdminLoginForm, LoginForm, SignupForm, ProfileSettingsForm, CompleteProfileForm
from .routing import next_step_url_name
from .codes import generate_code, check_code, cooldown_active, clear_generation_cooldown
from .emails import (
    send_welcome_email,
    send_login_2fa_email,
    send_password_reset_email,
    send_signup_verification_email,
)
from .oauth import build_google_auth_url, exchange_code_for_token, fetch_google_userinfo

UserModel = get_user_model()

PENDING_LOGIN_SESSION_KEY = "pending_2fa_user_id"
PENDING_RESET_SESSION_KEY = "pending_reset_user_id"
PENDING_SIGNUP_SESSION_KEY = "pending_signup_user_id"
SIGNUP_CODE_PURPOSE = "email_signup"
LOGIN_CODE_PURPOSE = "login_2fa"
RESET_CODE_PURPOSE = "password_reset"
GOOGLE_OAUTH_STATE_SESSION_KEY = "google_oauth_state"
# True for a missing account and for a delivery failure, so the wording
# does not reveal whether the address exists or claim that mail went out.
RESET_REQUEST_MESSAGE = (
    "If that email is registered, a reset code will be sent when email delivery succeeds."
)


def _safe_next(request, fallback):
    target = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if target and url_has_allowed_host_and_scheme(
        url=target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target
    return fallback


def _apply_signup_details(user, cleaned):
    user.username = cleaned["username"]
    user.date_of_birth = cleaned["date_of_birth"]
    user.cyber_class = cleaned["cyber_class"]
    user.skill_level = cleaned["skill_level"]
    user.ethical_agreement = cleaned["ethical_agreement"]
    user.email_verified = False
    user.is_active = False
    user.set_password(cleaned["password"])
    user.save()
    return user


def _send_signup_code(request, user):
    """Email a signup code. Never reports success when the backend did not accept it."""
    if cooldown_active(user, SIGNUP_CODE_PURPOSE):
        messages.error(request, "Please wait a moment before requesting another code.")
        return False
    code = generate_code(user, purpose=SIGNUP_CODE_PURPOSE)
    if not send_signup_verification_email(user, code.code):
        clear_generation_cooldown(user, SIGNUP_CODE_PURPOSE)
        messages.error(request, "We could not send the verification email. Please try again.")
        return False
    messages.success(request, "We sent a verification code to your email.")
    return True


def _activate_verified_signup(request, user):
    user.email_verified = True
    user.is_active = True
    user.save(update_fields=["email_verified", "is_active"])
    request.session.pop(PENDING_SIGNUP_SESSION_KEY, None)
    login(request, user, backend="accounts.backends.EmailAuthBackend")
    user.record_daily_activity()
    try:
        send_welcome_email(user)
    except Exception:
        pass
    from notifications.utils import notify
    notify(user, "Welcome to CyberQuest! Complete your first course to unlock the games.")
    messages.success(request, f"Welcome to CyberQuest, {user.display_name()}!")
    return redirect(next_step_url_name(user))


@rate_limit(key_prefix="signup", limit=10, window_seconds=3600)
def signup_view(request):
    if request.user.is_authenticated:
        return redirect(next_step_url_name(request.user))

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            existing = UserModel.objects.filter(email__iexact=email).first()
            if existing is not None and not existing.email_verified:
                user = _apply_signup_details(existing, form.cleaned_data)
            else:
                user = UserModel.objects.create_user(
                    email=email,
                    password=form.cleaned_data["password"],
                    username=form.cleaned_data["username"],
                    date_of_birth=form.cleaned_data["date_of_birth"],
                    cyber_class=form.cleaned_data["cyber_class"],
                    skill_level=form.cleaned_data["skill_level"],
                    ethical_agreement=form.cleaned_data["ethical_agreement"],
                    email_verified=False,
                    is_active=False,
                )
            request.session[PENDING_SIGNUP_SESSION_KEY] = user.pk
            _send_signup_code(request, user)
            return redirect("accounts:verify_email")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})


@rate_limit(key_prefix="verify_email", limit=30, window_seconds=900)
def verify_email_view(request):
    """Finish password signup only after the emailed code matches."""
    if request.user.is_authenticated:
        return redirect(next_step_url_name(request.user))

    pending_user_id = request.session.get(PENDING_SIGNUP_SESSION_KEY)
    user = UserModel.objects.filter(pk=pending_user_id).first() if pending_user_id else None
    if user is None:
        messages.error(request, "Submit the signup form before entering a verification code.")
        return redirect("accounts:signup")
    if user.email_verified:
        request.session.pop(PENDING_SIGNUP_SESSION_KEY, None)
        messages.success(request, "That email is already verified. Please log in.")
        return redirect("accounts:login")

    if request.method == "POST":
        if "resend" in request.POST:
            _send_signup_code(request, user)
        else:
            submitted_code = request.POST.get("code", "")
            if check_code(user, purpose=SIGNUP_CODE_PURPOSE, submitted_code=submitted_code):
                return _activate_verified_signup(request, user)
            messages.error(request, "Incorrect or expired code. Please try again.")

    return render(request, "accounts/verify_email.html", {"email": user.email})


@rate_limit(key_prefix="login", limit=20, window_seconds=900)
def login_view(request):
    if request.user.is_authenticated:
        return redirect(next_step_url_name(request.user))

    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]
            try:
                user = UserModel.objects.get(email__iexact=email)
            except UserModel.DoesNotExist:
                user = None

            if user is None or not user.has_usable_password() or not user.check_password(password):
                messages.error(request, "Invalid email or password.")
            elif not user.email_verified:
                request.session[PENDING_SIGNUP_SESSION_KEY] = user.pk
                if cooldown_active(user, SIGNUP_CODE_PURPOSE):
                    messages.info(request, "Enter the verification code we already sent to your email.")
                else:
                    _send_signup_code(request, user)
                return redirect("accounts:verify_email")
            elif not user.is_active:
                messages.error(request, "Your account has been suspended. Please contact support if you believe this is a mistake.")
            else:
                if user.totp_enabled:
                    request.session[PENDING_LOGIN_SESSION_KEY] = user.pk
                    request.session["pending_auth"] = "totp"
                    return redirect("accounts:verify_totp")
                if user.email_2fa_enabled:
                    code = generate_code(user, purpose=LOGIN_CODE_PURPOSE)
                    if not send_login_2fa_email(user, code.code):
                        clear_generation_cooldown(user, LOGIN_CODE_PURPOSE)
                        messages.error(
                            request,
                            "We could not send the login verification email. Please try again.",
                        )
                        return render(request, "accounts/login.html", {"form": form})
                    request.session[PENDING_LOGIN_SESSION_KEY] = user.pk
                    return redirect("accounts:verify_login")
                login(request, user, backend="accounts.backends.EmailAuthBackend")
                user.record_daily_activity()
                messages.success(request, f"Welcome back, {user.email}!")
                return redirect(next_step_url_name(user))
    else:
        form = LoginForm()
    return render(request, "accounts/login.html", {"form": form})


@rate_limit(key_prefix="admin_login", limit=20, window_seconds=900)
def admin_login_view(request):
    """Password sign-in for superusers. Students and staff are not signed in here."""
    fallback = reverse("ops:overview")
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect(_safe_next(request, fallback))
        return redirect(next_step_url_name(request.user))

    form = AdminLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        try:
            user = UserModel.objects.get(email__iexact=email)
        except UserModel.DoesNotExist:
            user = None
        if user is None or not user.has_usable_password() or not user.check_password(password):
            messages.error(request, "Invalid email or password.")
        elif not user.is_active:
            messages.error(request, "This administrator account is suspended.")
        elif not user.is_superuser:
            messages.error(request, "This sign-in is only for CyberQuest administrators.")
        else:
            login(request, user, backend="accounts.backends.EmailAuthBackend")
            user.record_daily_activity()
            return redirect(_safe_next(request, fallback))
    return render(request, "accounts/admin_login.html", {
        "form": form,
        "next": request.POST.get("next") or request.GET.get("next") or "",
    })


@rate_limit(key_prefix="verify_login", limit=30, window_seconds=900)
def verify_login_pin(request):
    pending_user_id = request.session.get(PENDING_LOGIN_SESSION_KEY)
    if not pending_user_id:
        messages.error(request, "Please log in first.")
        return redirect("accounts:login")

    user = UserModel.objects.filter(pk=pending_user_id).first()
    if user is None:
        del request.session[PENDING_LOGIN_SESSION_KEY]
        return redirect("accounts:login")

    if request.method == "POST":
        if "resend" in request.POST:
            code = generate_code(user, purpose=LOGIN_CODE_PURPOSE)
            if send_login_2fa_email(user, code.code):
                messages.success(request, "A new code has been sent to your email.")
            else:
                clear_generation_cooldown(user, LOGIN_CODE_PURPOSE)
                messages.error(
                    request,
                    "We could not send the login verification email. Please try again.",
                )
        else:
            submitted_code = request.POST.get("code", "")
            if check_code(user, purpose=LOGIN_CODE_PURPOSE, submitted_code=submitted_code):
                del request.session[PENDING_LOGIN_SESSION_KEY]
                login(request, user, backend="accounts.backends.EmailAuthBackend")
                user.record_daily_activity()
                messages.success(request, f"Welcome back, {user.email}!")
                return redirect(next_step_url_name(user))
            else:
                messages.error(request, "Incorrect or expired code. Please try again.")

    return render(request, "accounts/verify_login.html", {"email": user.email})


@rate_limit(key_prefix="forgot_password", limit=8, window_seconds=3600)
def forgot_password_view(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        user = UserModel.objects.filter(email__iexact=email).first()
        if user is not None and user.has_usable_password():
            code = generate_code(user, purpose=RESET_CODE_PURPOSE)
            if send_password_reset_email(user, code.code):
                request.session[PENDING_RESET_SESSION_KEY] = user.pk
            else:
                # The code never left the server. Drop it so a later request
                # can send a new one, and do not open the reset form.
                clear_generation_cooldown(user, RESET_CODE_PURPOSE)
                code.is_used = True
                code.save(update_fields=["is_used"])
        messages.success(request, RESET_REQUEST_MESSAGE)
        return redirect("accounts:reset_password")
    return render(request, "accounts/forgot_password.html")


@rate_limit(key_prefix="reset_password", limit=30, window_seconds=900)
def reset_password_view(request):
    pending_user_id = request.session.get(PENDING_RESET_SESSION_KEY)
    if not pending_user_id:
        messages.error(request, "Please request a password reset code first.")
        return redirect("accounts:forgot_password")

    user = UserModel.objects.filter(pk=pending_user_id).first()

    if request.method == "POST" and user is not None:
        submitted_code = request.POST.get("code", "")
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")

        password_error = ""
        confirm_error = ""
        if new_password != confirm_password:
            confirm_error = "Passwords do not match."
        else:
            try:
                validate_password(new_password, user=user)
            except ValidationError as exc:
                password_error = " ".join(exc.messages)
        if password_error or confirm_error:
            return render(request, "accounts/reset_password.html", {
                "password_error": password_error,
                "confirm_error": confirm_error,
            })
        if not check_code(user, purpose=RESET_CODE_PURPOSE, submitted_code=submitted_code):
            messages.error(request, "Incorrect or expired code.")
        else:
            user.set_password(new_password)
            user.save(update_fields=["password"])
            del request.session[PENDING_RESET_SESSION_KEY]
            messages.success(request, "Password reset successfully. Please log in.")
            return redirect("accounts:login")

    return render(request, "accounts/reset_password.html")


@login_required(login_url="/accounts/login/")
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("pages:home")


@login_required(login_url="/accounts/login/")
def profile_settings(request):
    """
    Authenticated users edit ONLY their own profile (request.user).
    Supports saving personal fields, uploading/replacing a photo, and
    permanently removing the current profile picture from storage.
    """
    user = request.user

    if request.method == "POST" and "remove_photo" in request.POST:
        if user.profile_picture:
            user.profile_picture.delete(save=False)
            user.profile_picture = None
            user.save(update_fields=["profile_picture"])
            messages.success(request, "Profile picture removed.")
        return redirect("accounts:settings")

    if request.method == "POST":
        old_picture_name = user.profile_picture.name if user.profile_picture else None
        form = ProfileSettingsForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            updated_user = form.save(commit=False)
            # Never allow privilege / gamification fields through this path.
            updated_user.save(update_fields=[
                "profile_picture",
                "full_name",
                "username",
                "date_of_birth",
                "cyber_class",
                "skill_level",
            ])
            # If a new image replaced an old one, delete the orphaned file.
            new_picture_name = (
                updated_user.profile_picture.name if updated_user.profile_picture else None
            )
            if old_picture_name and new_picture_name and old_picture_name != new_picture_name:
                from django.core.files.storage import default_storage
                if default_storage.exists(old_picture_name):
                    default_storage.delete(old_picture_name)
            messages.success(request, "Profile updated successfully.")
            return redirect("accounts:settings")
    else:
        form = ProfileSettingsForm(instance=user)

    return render(request, "accounts/profile_settings.html", {
        "form": form,
        "user_email": user.email,
        "google_linked": user.google_linked,
        "totp_enabled": user.totp_enabled,
        "email_2fa_enabled": user.email_2fa_enabled,
        "has_password": user.has_usable_password(),
    })


# ============================================================
# GOOGLE SIGN-IN
# ============================================================

def google_login_start(request):
    """Step 1: send the user to Google's own consent screen."""
    state = secrets.token_urlsafe(24)
    request.session[GOOGLE_OAUTH_STATE_SESSION_KEY] = state
    redirect_uri = request.build_absolute_uri(reverse("accounts:google_callback"))
    return redirect(build_google_auth_url(state, redirect_uri))


def google_login_callback(request):
    """Step 2: Google redirects back here with a one-time code (or an error)."""

    if request.GET.get("error"):
        messages.error(request, "Google sign-in was cancelled.")
        return redirect("accounts:login")

    returned_state = request.GET.get("state")
    expected_state = request.session.pop(GOOGLE_OAUTH_STATE_SESSION_KEY, None)
    # Comparing against a value WE generated and stored server-side (not
    # trusting anything the browser sends alone) -- this is what stops an
    # attacker from tricking a user into completing someone else's OAuth flow.
    if not returned_state or returned_state != expected_state:
        messages.error(request, "Invalid sign-in attempt. Please try again.")
        return redirect("accounts:login")

    code = request.GET.get("code")
    if not code:
        messages.error(request, "Google sign-in failed. Please try again.")
        return redirect("accounts:login")

    redirect_uri = request.build_absolute_uri(reverse("accounts:google_callback"))
    try:
        token_data = exchange_code_for_token(code, redirect_uri)
        userinfo = fetch_google_userinfo(token_data["access_token"])
    except (requests.RequestException, KeyError):
        messages.error(request, "Could not connect to Google. Please try again.")
        return redirect("accounts:login")

    if not userinfo.get("email_verified"):
        messages.error(request, "Your Google email address is not verified.")
        return redirect("accounts:login")

    email = userinfo["email"]
    user = UserModel.objects.filter(email__iexact=email).first()
    created = False

    if user is None:
        created = True
        base_username = email.split("@")[0]
        username = base_username
        suffix = 1
        while UserModel.objects.filter(username__iexact=username).exists():
            suffix += 1
            username = f"{base_username}{suffix}"

        user = UserModel.objects.create_user(
            email=email, password=None,  # -> set_unusable_password() inside create_user
            username=username, full_name=userinfo.get("name", ""), google_linked=True,
        )

        # Best-effort: pull their Google avatar in as a starting profile
        # picture. Never blocks account creation if this fails.
        picture_url = userinfo.get("picture")
        if picture_url:
            try:
                img_response = requests.get(picture_url, timeout=10)
                if img_response.status_code == 200:
                    user.profile_picture.save(
                        f"google_{user.pk}.jpg", ContentFile(img_response.content), save=True
                    )
            except requests.RequestException:
                pass
    elif not user.email_verified:
        request.session[PENDING_SIGNUP_SESSION_KEY] = user.pk
        if cooldown_active(user, SIGNUP_CODE_PURPOSE):
            messages.info(request, "Enter the verification code we already sent to your email.")
        else:
            _send_signup_code(request, user)
        messages.error(request, "Verify your email with the signup code before using this account.")
        return redirect("accounts:verify_email")
    elif not user.google_linked:
        user.google_linked = True
        user.save(update_fields=["google_linked"])

    if not user.is_active:
        messages.error(request, "Your account has been suspended. Please contact support if you believe this is a mistake.")
        return redirect("accounts:login")

    if user.totp_enabled:
        request.session[PENDING_LOGIN_SESSION_KEY] = user.pk
        request.session["pending_auth"] = "totp"
        messages.info(request, "Enter the code from your authenticator app to finish signing in.")
        return redirect("accounts:verify_totp")

    login(request, user, backend="accounts.backends.EmailAuthBackend")
    user.record_daily_activity()

    if created:
        send_welcome_email(user)
        from notifications.utils import notify
        notify(user, "Welcome to CyberQuest! Please complete your profile to get started.")
        messages.success(request, f"Welcome to CyberQuest, {user.display_name()}!")
    else:
        messages.success(request, f"Welcome back, {user.email}!")

    return redirect(next_step_url_name(user))


@login_required(login_url="/accounts/login/")
def complete_profile_view(request):
    """
    Shown once to Google sign-ups (or anyone else missing the CyberQuest-
    specific fields our normal signup form collects). Skipped entirely
    for regular email/password users, since they already filled this in
    at signup.
    """
    if request.user.ethical_agreement:
        # Already complete -- nothing to do here, send them onward.
        return redirect(next_step_url_name(request.user))

    if request.method == "POST":
        form = CompleteProfileForm(request.POST, user=request.user)
        if form.is_valid():
            user = request.user
            chosen = form.cleaned_data.get("username") or ""
            fields = ["date_of_birth", "cyber_class", "skill_level", "ethical_agreement"]
            user.date_of_birth = form.cleaned_data["date_of_birth"]
            user.cyber_class = form.cleaned_data["cyber_class"]
            user.skill_level = form.cleaned_data["skill_level"]
            user.ethical_agreement = form.cleaned_data["ethical_agreement"]
            if chosen:
                user.username = chosen
                fields.append("username")
            user.save(update_fields=fields)
            messages.success(request, "Profile complete!")
            return redirect(next_step_url_name(user))
    else:
        form = CompleteProfileForm(user=request.user, initial={"username": request.user.username or ""})

    return render(request, "accounts/complete_profile.html", {"form": form})


def _totp_locked(request) -> bool:
    from django.utils import timezone
    until = request.session.get("totp_lock_until")
    return bool(until and timezone.now().timestamp() < until)


def _totp_register_failure(request) -> None:
    from django.utils import timezone
    fails = request.session.get("totp_fails", 0) + 1
    request.session["totp_fails"] = fails
    if fails >= 5:
        request.session["totp_lock_until"] = timezone.now().timestamp() + 300
        request.session["totp_fails"] = 0


def verify_totp_login(request):
    from .totp import consume_recovery_code, verify_totp

    pending_user_id = request.session.get(PENDING_LOGIN_SESSION_KEY)
    if request.session.get("pending_auth") != "totp" or not pending_user_id:
        messages.error(request, "Please log in first.")
        return redirect("accounts:login")
    user = UserModel.objects.filter(pk=pending_user_id, totp_enabled=True).first()
    if user is None:
        request.session.pop(PENDING_LOGIN_SESSION_KEY, None)
        request.session.pop("pending_auth", None)
        return redirect("accounts:login")

    if request.method == "POST":
        if _totp_locked(request):
            messages.error(request, "Too many attempts. Wait five minutes and try again.")
        else:
            code = request.POST.get("code", "")
            ok = verify_totp(user.totp_secret, code) or consume_recovery_code(user, code)
            if ok:
                request.session.pop(PENDING_LOGIN_SESSION_KEY, None)
                request.session.pop("pending_auth", None)
                request.session.pop("totp_fails", None)
                request.session.pop("totp_lock_until", None)
                login(request, user, backend="accounts.backends.EmailAuthBackend")
                user.record_daily_activity()
                messages.success(request, f"Welcome back, {user.email}!")
                return redirect(next_step_url_name(user))
            _totp_register_failure(request)
            messages.error(request, "Incorrect authenticator or recovery code.")
    return render(request, "accounts/verify_totp.html", {"email": user.email})


@login_required(login_url="/accounts/login/")
def email_2fa_toggle(request):
    """Turn the email login code on or off. Off unless the user chooses it."""
    if request.method != "POST":
        return redirect("accounts:settings")
    user = request.user
    turn_on = request.POST.get("enabled") == "1"
    if turn_on and not user.has_usable_password():
        messages.error(request, "Email login codes only apply when you sign in with a password.")
        return redirect("accounts:settings")
    user.email_2fa_enabled = turn_on
    user.save(update_fields=["email_2fa_enabled"])
    if turn_on:
        messages.success(request, "Email login codes are on. The next password sign-in will email you a code.")
    else:
        messages.success(request, "Email login codes are off. Password sign-in no longer asks for a code.")
    return redirect("accounts:settings")


@login_required(login_url="/accounts/login/")
def totp_start(request):
    import base64
    import io
    import qrcode
    from .totp import new_secret, provisioning_uri

    if request.user.totp_enabled:
        messages.info(request, "Two-factor authentication is already enabled.")
        return redirect("accounts:settings")
    secret = request.session.get("pending_totp_secret")
    if request.method == "POST" or not secret:
        if request.method != "POST":
            return redirect("accounts:settings")
        secret = new_secret()
        request.session["pending_totp_secret"] = secret
    uri = provisioning_uri(secret, request.user.email)
    image = qrcode.make(uri)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    qr = base64.b64encode(buffer.getvalue()).decode("ascii")
    return render(request, "accounts/totp_setup.html", {
        "secret": secret,
        "qr_data_uri": f"data:image/png;base64,{qr}",
    })


@login_required(login_url="/accounts/login/")
def totp_confirm(request):
    from .totp import issue_recovery_codes, verify_totp

    secret = request.session.get("pending_totp_secret")
    if not secret:
        messages.error(request, "Start two-factor setup again.")
        return redirect("accounts:settings")
    if request.method != "POST":
        return redirect("accounts:totp_start")
    if _totp_locked(request):
        messages.error(request, "Too many attempts. Wait five minutes and try again.")
        return redirect("accounts:settings")
    if not verify_totp(secret, request.POST.get("code", "")):
        _totp_register_failure(request)
        messages.error(request, "That code did not match. Two-factor authentication is still off.")
        return redirect("accounts:settings")
    user = request.user
    user.totp_secret = secret
    user.totp_enabled = True
    user.save(update_fields=["totp_secret", "totp_enabled"])
    codes = issue_recovery_codes(user)
    request.session.pop("pending_totp_secret", None)
    request.session.pop("totp_fails", None)
    return render(request, "accounts/totp_recovery.html", {"codes": codes})


@login_required(login_url="/accounts/login/")
def totp_disable(request):
    from .totp import verify_totp

    if request.method != "POST":
        return redirect("accounts:settings")
    user = request.user
    password = request.POST.get("password", "")
    code = request.POST.get("code", "")
    password_ok = user.has_usable_password() and user.check_password(password)
    code_ok = verify_totp(user.totp_secret, code)
    if not password_ok and not code_ok:
        messages.error(request, "Enter your password or a current authenticator code to turn off 2FA.")
        return redirect("accounts:settings")
    user.totp_enabled = False
    user.totp_secret = ""
    user.save(update_fields=["totp_enabled", "totp_secret"])
    user.recovery_codes.all().delete()
    messages.success(request, "Two-factor authentication is now off.")
    return redirect("accounts:settings")


@login_required(login_url="/accounts/login/")
def profile_photo(request, pk):
    """Serve one user's profile photo to any signed-in member. No client path is accepted."""
    from django.http import Http404

    from cyberquest.media_access import serve_stored_file

    owner = UserModel.objects.filter(pk=pk).first()
    if owner is None or not owner.profile_picture:
        raise Http404("Profile photo not found.")
    response = serve_stored_file(owner.profile_picture)
    if response is None:
        raise Http404("Profile photo not found.")
    return response
