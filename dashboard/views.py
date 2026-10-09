from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render
from .analytics import analytics_payload
from .utils import get_dashboard_context, build_radar_points


@login_required(login_url="/accounts/login/")
def dashboard_home(request):
    context = get_dashboard_context(request.user)
    radar_skills = [s for s in context["skill_matrix"] if not s.get("coming_soon")]
    percentages = [s["percent"] for s in radar_skills]
    data_points, label_points, grid_rings = build_radar_points(percentages)
    context["radar_data_points"] = data_points
    context["radar_label_points"] = list(zip(radar_skills, label_points))
    context["radar_grid_rings"] = grid_rings

    return render(request, "dashboard/dashboard.html", context)


@login_required(login_url="/accounts/login/")
def admin_analytics(request):
    if not request.user.is_staff:
        return HttpResponseForbidden("Staff only.")
    try:
        days = int(request.GET.get("days", "30"))
    except ValueError:
        days = 30
    return render(request, "dashboard/admin_analytics.html", analytics_payload(days))
