from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from courses.progress import has_completed_all_courses
from .utils import get_dashboard_context, build_radar_points


@login_required(login_url="/accounts/login/")
def dashboard_home(request):
    if not has_completed_all_courses(request.user):
        messages.error(request, "Please complete the course introduction first.")
        return redirect("courses:intro")

    context = get_dashboard_context(request.user)
    percentages = [s["percent"] for s in context["skill_matrix"]]
    data_points, label_points, grid_rings = build_radar_points(percentages)
    context["radar_data_points"] = data_points
    context["radar_label_points"] = list(zip(context["skill_matrix"], label_points))
    context["radar_grid_rings"] = grid_rings

    return render(request, "dashboard/dashboard.html", context)
