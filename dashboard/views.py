"""
dashboard/views.py
---------------------
Handles the logged-in user's home screen.

This file only decides WHAT to show once someone is authenticated.
It does not know anything about login/logout logic -- that's the
accounts app's job. This is the separation you asked for: each feature
only knows about its own responsibility.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages

from courses.progress import has_completed_all_courses


@login_required(login_url="/accounts/login/")
def dashboard_home(request):
    """
    Show the dashboard. @login_required means:
      - if the user IS logged in  -> this function runs normally
      - if the user is NOT logged in -> Django auto-redirects them to
        LOGIN_URL (set in settings.py) instead of ever running this code
    """

    user = request.user

    # Enforce the learning path: dashboard (and therefore games, which are
    # only reachable FROM the dashboard) requires the course intro first.
    if not has_completed_all_courses(user):
        messages.error(request, "Please complete the course introduction first.")
        return redirect("courses:intro")

    # Simple XP-to-next-level math for a progress bar (100 XP per level)
    xp_for_next_level = 100
    xp_progress_percent = min(int((user.xp % xp_for_next_level) / xp_for_next_level * 100), 100)

    context = {
        "user_email": user.email,
        "display_name": user.display_name(),
        "username": user.username,
        "cyber_class_label": user.get_cyber_class_display(),
        "skill_level_label": user.get_skill_level_display(),
        "date_joined": user.date_joined,
        "xp": user.xp,
        "level": user.level,
        "xp_progress_percent": xp_progress_percent,
    }

    return render(request, "dashboard/dashboard.html", context)
