from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from courses.progress import has_completed_all_courses


@login_required(login_url="/accounts/login/")
def dashboard_home(request):
    user = request.user

    if not has_completed_all_courses(user):
        messages.error(request, "Please complete the course introduction first.")
        return redirect("courses:intro")

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
        "profile_picture": user.profile_picture,
    }
    return render(request, "dashboard/dashboard.html", context)
