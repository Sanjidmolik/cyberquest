from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.http import Http404

from games.views import _apply_xp_and_level_up
from .models import PracticeSession
from .scenarios import DOMAIN_BY_SLUG, get_scenario, get_domain_scenario
from .engine import apply_action, open_workspace, build_console_context, session_state
from .adaptive import (
    build_practice_center_context,
    get_cyber_dna,
    get_recommendation,
    recommended_difficulty,
    get_domain_competencies,
)

XP_PRACTICE_COMPLETE = 40


@login_required(login_url="/accounts/login/")
def practice_center(request):
    ctx = build_practice_center_context(request.user)
    return render(request, "practice/center.html", ctx)


@login_required(login_url="/accounts/login/")
def domain_detail(request, domain):
    meta = DOMAIN_BY_SLUG.get(domain)
    if not meta:
        raise Http404("Unknown domain.")

    domains = get_domain_competencies(request.user)
    row = next(d for d in domains if d["slug"] == domain)
    scenario = get_domain_scenario(domain)
    return render(request, "practice/domain.html", {
        "domain": row,
        "scenario": scenario,
        "recommendation": get_recommendation(request.user),
    })


@login_required(login_url="/accounts/login/")
@require_POST
def start_practice(request, domain):
    meta = DOMAIN_BY_SLUG.get(domain)
    if not meta:
        raise Http404("Unknown domain.")

    activity = request.POST.get("activity_type", "simulation")
    if activity not in ("simulation", "incident", "game"):
        messages.error(request, "Invalid activity type.")
        return redirect("practice:domain", domain=domain)

    if activity == "game":
        return redirect(meta["game_url"])

    scenario = get_domain_scenario(domain)
    if not scenario:
        messages.error(request, "No scenario available for this domain.")
        return redirect("practice:center")

    comps = get_domain_competencies(request.user)
    row = next(d for d in comps if d["slug"] == domain)
    difficulty = request.POST.get("difficulty") or row["difficulty"]
    if difficulty not in ("beginner", "intermediate", "advanced"):
        difficulty = recommended_difficulty(row["percent"])

    session = PracticeSession.objects.create(
        user=request.user,
        domain=domain,
        activity_type=activity,
        scenario_key=scenario["key"],
        difficulty=difficulty,
        score=0,
        max_score=100,
        decisions=[],
        state={"phase": "briefing", "revealed": []},
        status="in_progress",
    )
    return redirect("practice:play", session_id=session.pk)


@login_required(login_url="/accounts/login/")
def play_session(request, session_id):
    session = get_object_or_404(PracticeSession, pk=session_id, user=request.user)
    scenario = get_scenario(session.scenario_key)
    if not scenario:
        raise Http404("Scenario missing.")

    if session.status == "completed":
        return redirect("practice:result", session_id=session.pk)

    console = build_console_context(session, scenario)
    domain = DOMAIN_BY_SLUG.get(session.domain, {})
    return render(request, "practice/play.html", {
        "session": session,
        "scenario": scenario,
        "domain": domain,
        "is_incident": session.activity_type == "incident",
        **console,
    })


@login_required(login_url="/accounts/login/")
@require_POST
def open_console(request, session_id):
    session = get_object_or_404(PracticeSession, pk=session_id, user=request.user)
    try:
        open_workspace(session)
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("practice:play", session_id=session.pk)


@login_required(login_url="/accounts/login/")
@require_POST
def submit_decision(request, session_id):
    session = get_object_or_404(PracticeSession, pk=session_id, user=request.user)
    action_key = (request.POST.get("action") or "").strip()

    try:
        result = apply_action(session, action_key)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("practice:play", session_id=session.pk)

    if result.get("ended"):
        session.refresh_from_db()
        if session.xp_awarded == 0:
            xp = max(10, round(session.percent / 100 * XP_PRACTICE_COMPLETE))
            leveled = _apply_xp_and_level_up(request.user, xp)
            session.xp_awarded = xp
            session.save(update_fields=["xp_awarded"])
            messages.success(request, f"+{xp} XP earned!")
            if leveled:
                messages.success(request, f"Level up! You're now Level {request.user.level}.")
        return redirect("practice:result", session_id=session.pk)

    return redirect("practice:play", session_id=session.pk)


@login_required(login_url="/accounts/login/")
def practice_result(request, session_id):
    session = get_object_or_404(PracticeSession, pk=session_id, user=request.user)
    if session.status != "completed":
        return redirect("practice:play", session_id=session.pk)

    scenario = get_scenario(session.scenario_key)
    state = session_state(session)
    consequence = state.get("consequence") or {}
    required = scenario.get("required_evidence") or []
    revealed = set(state.get("revealed") or [])
    inv = scenario.get("investigations", {})

    evidence_status = []
    for key in required:
        evidence_status.append({
            "label": inv[key]["label"] if key in inv else key,
            "collected": key in revealed,
        })

    investigation_score = sum(
        d.get("score_delta", 0) for d in (session.decisions or []) if d.get("type") == "investigate"
    )

    return render(request, "practice/result.html", {
        "session": session,
        "scenario": scenario,
        "domain": DOMAIN_BY_SLUG.get(session.domain, {}),
        "recommendation": get_recommendation(request.user),
        "cyber_dna": get_cyber_dna(request.user),
        "consequence": consequence,
        "evidence_status": evidence_status,
        "investigation_score": max(0, investigation_score),
    })


@login_required(login_url="/accounts/login/")
def cyber_dna_view(request):
    return render(request, "practice/cyber_dna.html", {
        "cyber_dna": get_cyber_dna(request.user),
        "recommendation": get_recommendation(request.user),
    })


@login_required(login_url="/accounts/login/")
def practice_history(request):
    sessions = PracticeSession.objects.filter(
        user=request.user, status="completed"
    ).order_by("-completed_at", "-created_at")[:50]
    return render(request, "practice/history.html", {"sessions": sessions})
