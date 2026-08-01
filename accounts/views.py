"""
accounts/views.py
--------------------
Handles WHAT HAPPENS on each request to the login/logout URLs.

This file intentionally does NOT contain:
  - email validation rules      -> validators.py
  - the actual password check   -> backends.py
  - form field definitions      -> forms.py
It only wires those pieces together and decides what to show the user.
"""

from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages

from .forms import LoginForm, SignupForm
from .routing import next_step_url_name

UserModel = get_user_model()


def signup_view(request):
    """
    Show the signup page (GET) and create the account (POST).
    On success, logs the new user in immediately and sends them to the
    dashboard -- no separate "verify your email" step for now.
    """

    if request.user.is_authenticated:
        return redirect(next_step_url_name(request.user))

    if request.method == "POST":
        form = SignupForm(request.POST)

        if form.is_valid():
            # form.is_valid() already confirmed: valid domain, email not
            # taken, username not taken, passwords match, age >= 13
            email = form.cleaned_data["email"]
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            date_of_birth = form.cleaned_data["date_of_birth"]
            cyber_class = form.cleaned_data["cyber_class"]
            skill_level = form.cleaned_data["skill_level"]
            ethical_agreement = form.cleaned_data["ethical_agreement"]

            # create_user() hashes the password for us (see models.py)
            user = UserModel.objects.create_user(
                email=email,
                password=password,
                username=username,
                date_of_birth=date_of_birth,
                cyber_class=cyber_class,
                skill_level=skill_level,
                ethical_agreement=ethical_agreement,
            )

            # We must specify which backend to use here, since settings.py
            # configures TWO backends (our EmailAuthBackend + Django's
            # default ModelBackend for /admin/). We didn't just come from
            # authenticate(), so Django doesn't know which one applies.
            login(request, user, backend="accounts.backends.EmailAuthBackend")
            messages.success(request, f"Welcome to CyberQuest, {user.display_name()}!")
            # New accounts always start at the course intro -- course_intro_completed
            # defaults to False, so next_step_url_name() sends them there first.
            return redirect(next_step_url_name(user))
        # if invalid, form errors (bad domain, email taken, password
        # mismatch, etc.) are shown automatically in the template
    else:
        form = SignupForm()

    return render(request, "accounts/signup.html", {"form": form})


def login_view(request):
    """
    Show the login page (GET) and process the login attempt (POST).
    """

    # If the user is already logged in, send them to whatever step is next.
    if request.user.is_authenticated:
        return redirect(next_step_url_name(request.user))

    if request.method == "POST":
        form = LoginForm(request.POST)

        if form.is_valid():
            # form.is_valid() ALSO ran our email-domain check (forms.py -> validators.py)
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]

            # authenticate() calls OUR backend in backends.py behind the scenes
            user = authenticate(request, email=email, password=password)

            if user is not None:
                login(request, user)  # creates the logged-in session
                messages.success(request, f"Welcome back, {user.email}!")
                # Enforced learning path: unread course -> course intro, else dashboard
                return redirect(next_step_url_name(user))
            else:
                # Email format/domain was fine, but email+password didn't match
                # any account. Keep the message generic for security.
                messages.error(request, "Invalid email or password.")
        # If form.is_valid() is False, Django automatically attaches the
        # validator's error message (e.g. "Only Gmail, Hotmail... allowed")
        # to the template via {{ form.email.errors }}

    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form})


@login_required(login_url="/accounts/login/")
def logout_view(request):
    """Log the current user out and send them back to the login page."""
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("accounts:login")
