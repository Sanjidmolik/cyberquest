from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.http import Http404

from achievements.checks import check_and_award_badges
from games.views import _apply_xp_and_level_up
from .models import PracticeSession
from .scenarios import (
    DOMAIN_BY_SLUG,
    choose_scenario,
    get_scenario,
    get_domain_scenario,
    scenarios_for_domain,
)
from .engine import apply_action, open_workspace, build_console_context, session_state
from .adaptive import (
    build_practice_center_context,
    get_cyber_dna,
    get_recommendation,
    get_domain_competencies,
)

XP_PRACTICE_COMPLETE = 50
_SCENARIO_MINUTES = {"beginner": 12, "intermediate": 15, "advanced": 18}


def award_practice_completion(user, session):
    """Award 50 XP once for a completed session. Score does not change the amount."""
    with transaction.atomic():
        locked_session = PracticeSession.objects.select_for_update().get(pk=session.pk)
        if locked_session.user_id != getattr(user, "pk", None):
            return 0, False
        if locked_session.status != "completed" or locked_session.xp_awarded:
            session.xp_awarded = locked_session.xp_awarded
            return 0, False
        locked = get_user_model().objects.select_for_update().get(pk=user.pk)
        leveled = _apply_xp_and_level_up(locked, XP_PRACTICE_COMPLETE)
        locked_session.xp_awarded = XP_PRACTICE_COMPLETE
        locked_session.save(update_fields=["xp_awarded"])
        session.xp_awarded = XP_PRACTICE_COMPLETE
        user.xp = locked.xp
        user.level = locked.level
    return XP_PRACTICE_COMPLETE, leveled


def _recent_scenario_keys(user, domain):
    recent = []
    completed = (
        PracticeSession.objects.filter(user=user, domain=domain, status="completed")
        .order_by("-completed_at", "-pk")
        .only("scenario_key")
    )
    for row in completed:
        if row.scenario_key not in recent:
            recent.append(row.scenario_key)
    return recent


def _best_by_scenario(user):
    best = {}
    rows = PracticeSession.objects.filter(user=user, status="completed").only(
        "scenario_key", "score", "max_score",
    )
    for row in rows:
        best[row.scenario_key] = max(best.get(row.scenario_key, 0), row.percent)
    return best


def _center_catalog(user):
    best = _best_by_scenario(user)
    catalog = []
    for row in get_domain_competencies(user):
        preferred = choose_scenario(row["slug"], _recent_scenario_keys(user, row["slug"]))
        preferred_key = preferred["key"] if preferred else ""
        scenarios = []
        for index, scenario in enumerate(scenarios_for_domain(row["slug"]), start=1):
            scene = scenario.get("scene") or {}
            completed = scenario["key"] in best
            scenarios.append({
                "key": scenario["key"],
                "number": f"{index:02d}",
                "title": scenario["title"],
                "summary": scenario.get("briefing", {}).get("summary", ""),
                "activity": scenario.get("activity_type") or "simulation",
                "activity_label": (scenario.get("activity_type") or "simulation").replace("_", " ").title(),
                "difficulty": scenario.get("difficulty") or "beginner",
                "difficulty_label": (scenario.get("difficulty") or "beginner").title(),
                "minutes": _SCENARIO_MINUTES.get(scenario.get("difficulty"), 15),
                "objective": scenario.get("objective") or "",
                "completed": completed,
                "best": best.get(scenario["key"]) if completed else None,
                "preferred": scenario["key"] == preferred_key,
                "scene": {
                    "nodes": scene.get("nodes") or [],
                    "suspicious": scene.get("suspicious") or [],
                },
            })
        catalog.append({
            "slug": row["slug"],
            "full_label": row["full_label"],
            "emoji": row["emoji"],
            "percent": row["percent"],
            "level": row["level"],
            "activity_label": row["activity_label"],
            "difficulty_label": row["difficulty_label"],
            "scenario_count": len(scenarios),
            "start_url": reverse("practice:start", args=[row["slug"]]),
            "scenarios": scenarios,
        })
    return catalog


@login_required(login_url="/accounts/login/")
def practice_center(request):
    ctx = build_practice_center_context(request.user)
    catalog = _center_catalog(request.user)
    selected_slug = (ctx.get("recommendation") or {}).get("domain_slug") or "phishing"
    selected = next((row for row in catalog if row["slug"] == selected_slug), catalog[0])
    opening = next((s for s in selected["scenarios"] if s["preferred"]), selected["scenarios"][0])
    for row in ctx["domains"]:
        row["scenario_count"] = len(scenarios_for_domain(row["slug"]))
    return render(request, "practice/center.html", {
        **ctx,
        "catalog": catalog,
        "selected_domain": selected,
        "opening": opening,
    })


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
        "scenario_count": len(scenarios_for_domain(domain)),
        "recommendation": get_recommendation(request.user),
    })


@login_required(login_url="/accounts/login/")
@require_POST
def start_practice(request, domain):
    meta = DOMAIN_BY_SLUG.get(domain)
    if not meta:
        raise Http404("Unknown domain.")

    activity = (request.POST.get("activity_type") or "").strip()
    if activity == "game":
        return redirect(meta["game_url"])
    if activity and activity not in ("simulation", "incident"):
        messages.error(request, "Invalid activity type.")
        return redirect("practice:domain", domain=domain)

    requested = (request.POST.get("scenario_key") or "").strip()
    if requested:
        scenario = get_scenario(requested)
        if not scenario or scenario.get("domain") != domain:
            messages.error(request, "That scenario is not part of this practice topic.")
            return redirect("practice:center")
    else:
        scenario = choose_scenario(domain, _recent_scenario_keys(request.user, domain), activity or None)
    if not scenario:
        messages.error(request, "No scenario available for this domain.")
        return redirect("practice:center")

    session = PracticeSession.objects.create(
        user=request.user,
        domain=domain,
        activity_type=scenario.get("activity_type") or activity or "simulation",
        scenario_key=scenario["key"],
        difficulty=scenario.get("difficulty") or "beginner",
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
        xp, leveled = award_practice_completion(request.user, session)
        if xp:
            messages.success(request, f"+{xp} XP earned!")
            if leveled:
                messages.success(request, f"Level up! You're now Level {request.user.level}.")
            for badge in check_and_award_badges(request.user):
                messages.success(request, f"🏆 New badge unlocked: {badge.icon_emoji} {badge.name}!")
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
        "competency": _domain_competency_change(request.user, session),
        "consequence": consequence,
        "evidence_status": evidence_status,
        "investigation_score": max(0, investigation_score),
        "active_nodes": [
            (scenario.get("scene") or {}).get("evidence_nodes", {}).get(key)
            for key in revealed
            if (scenario.get("scene") or {}).get("evidence_nodes", {}).get(key)
        ],
        "focus_node": None,
        "outcome": consequence.get("quality") or "live",
    })


def _domain_competency_change(user, session):
    """Before/after for this session only. Current score comes from Cyber DNA."""
    rows = {row["slug"]: row for row in get_domain_competencies(user)}
    current = rows.get(session.domain)
    if not current:
        return None
    earlier_best = 0
    earlier = (
        PracticeSession.objects.filter(
            user=user, domain=session.domain, status="completed",
        )
        .exclude(pk=session.pk)
        .only("score", "max_score")
    )
    for row in earlier:
        earlier_best = max(earlier_best, row.percent)
    previous = max(current["game_percent"], earlier_best)
    now = current["percent"]
    return {
        "label": current["full_label"],
        "previous": previous,
        "current": now,
        "delta": now - previous,
        "improved": now > previous,
    }


@login_required(login_url="/accounts/login/")
def cyber_dna_view(request):
    return render(request, "practice/cyber_dna.html", {
        "cyber_dna": get_cyber_dna(request.user),
        "recommendation": get_recommendation(request.user),
    })


@login_required(login_url="/accounts/login/")
def practice_history(request):
    sessions = list(
        PracticeSession.objects.filter(
            user=request.user, status="completed"
        ).order_by("-completed_at", "-created_at")[:50]
    )
    for row in sessions:
        scenario = get_scenario(row.scenario_key)
        row.scenario_title = scenario["title"] if scenario else row.scenario_key
    return render(request, "practice/history.html", {"sessions": sessions})
