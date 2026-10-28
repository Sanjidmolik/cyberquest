from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .analytics import analytics_payload
from .career_engine import recommend_career
from .models import CareerRoadmap
from .ops_access import superuser_required
from .dashboard_data import build_dashboard_context
from .utils import get_dashboard_context


@login_required(login_url="/accounts/login/")
def dashboard_home(request):
    from games.attempts import finalize_expired_attempts
    finalize_expired_attempts(user=request.user)
    context = get_dashboard_context(request.user)
    # Bookshelf layout data (profile, books, skills, radar, ...) on top of the
    # base keys, which the top bar and shared sidebar still use.
    context.update(build_dashboard_context(request.user, context))
    return render(request, "dashboard/dashboard.html", context)


@login_required(login_url="/accounts/login/")
def career_compass(request):
    existing = CareerRoadmap.objects.filter(user=request.user).first()
    result = None
    errors = []

    if request.method == "POST":
        subject = request.POST.get("subject", "").strip()
        interests = request.POST.get("interests", "").strip()
        experience = request.POST.get("experience", "").strip()
        study_hours_raw = request.POST.get("study_hours", "5").strip()

        # Parse skills: skill_N / level_N pairs
        skills = []
        i = 0
        while True:
            skill = request.POST.get(f"skill_{i}", "").strip()
            level = request.POST.get(f"level_{i}", "beginner").strip()
            if not skill:
                break
            skills.append({"skill": skill, "level": level})
            i += 1

        try:
            study_hours = max(1, min(168, int(study_hours_raw)))
        except ValueError:
            study_hours = 5

        if not subject:
            errors.append("Please enter your university subject.")
        if not skills:
            errors.append("Please add at least one skill.")

        if not errors:
            result = recommend_career(subject, skills, interests, experience, study_hours)
            roadmap, _ = CareerRoadmap.objects.update_or_create(
                user=request.user,
                defaults={
                    "subject": subject,
                    "skills": skills,
                    "interests": interests,
                    "experience": experience,
                    "study_hours": study_hours,
                    "career_role": result["career_role"],
                    "skill_gaps": result["skill_gaps"],
                    "learning_roadmap": result["learning_roadmap"],
                },
            )
            existing = roadmap

    elif existing and existing.career_role:
        from .career_engine import ROLES
        role_meta = ROLES.get(existing.career_role, {})
        result = {
            "career_role": existing.career_role,
            "description": role_meta.get("description", ""),
            "certifications": role_meta.get("certifications", []),
            "avg_salary": role_meta.get("avg_salary", ""),
            "skill_gaps": existing.skill_gaps,
            "learning_roadmap": existing.learning_roadmap,
        }

    return render(request, "dashboard/career_compass.html", {
        "existing": existing,
        "result": result,
        "errors": errors,
    })


@superuser_required
def admin_analytics(request):
    try:
        days = int(request.GET.get("days", "30"))
    except ValueError:
        days = 30
    return render(request, "dashboard/admin_analytics.html", analytics_payload(days))
