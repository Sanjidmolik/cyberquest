from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.http import Http404

from .conversion import slug_for
from .models import Attempt, PracticeSession
from .scenarios import (
    DOMAIN_BY_SLUG,
    choose_scenario,
    get_scenario,
    scenarios_for_domain,
)
from .engine import session_state
from .adaptive import (
    build_practice_center_context,
    get_cyber_dna,
    get_recommendation,
    get_domain_competencies,
)

_SCENARIO_MINUTES = {"beginner": 12, "intermediate": 15, "advanced": 18}

# ---- Practice Center presentation only (no scoring or routing depends on these) ----
# Which existing practice topic belongs to which course, by stable course code.
# Courses without an entry have no practice scenarios yet.
_COURSE_PRACTICE_TOPIC = {
    "CQ-SAFETY": "safety", "MOD-01": "phishing", "MOD-02": "password", "CQ-MALWARE": "malware",
    "MOD-03": "network", "CQ-DEVICE": "device", "CQ-PRIVACY": "privacy", "CQ-RESPONSE": "response",
}
_COURSE_ICONS = {
    "CQ-SAFETY": "globe", "MOD-01": "mail", "MOD-02": "key", "CQ-MALWARE": "bug",
    "MOD-03": "wifi", "CQ-DEVICE": "phone", "CQ-PRIVACY": "eye", "CQ-RESPONSE": "siren",
}
# Existing comic artwork per practice topic: its mission illustration and its course cover.
_TOPIC_ART = {
    "phishing": ("games/mission-timer/assets/art/phishing.jpg", "courses/covers/cover_1.svg"),
    "password": ("games/mission-timer/assets/art/password.jpg", "courses/covers/cover_2.svg"),
    "network": ("games/mission-timer/assets/art/network.jpg", "courses/covers/cover_3.svg"),
    "cryptography": ("games/mission-timer/assets/art/crypto.jpg", "courses/covers/cover_4.svg"),
    "steganography": ("games/mission-timer/assets/art/stego.jpg", "courses/covers/cover_5.svg"),
    "osint": ("courses/covers/cover_6.svg", "courses/covers/cover_6.svg"),
    "safety": ("games/mission-timer/assets/art/stego.jpg", "courses/covers/cover_1.svg"),
    "malware": ("games/mission-timer/assets/art/network.jpg", "courses/covers/cover_4.svg"),
    "device": ("games/mission-timer/assets/art/password.jpg", "courses/covers/cover_6.svg"),
    "privacy": ("games/mission-timer/assets/art/stego.jpg", "courses/covers/cover_6.svg"),
    "response": ("games/mission-timer/assets/art/network.jpg", "courses/covers/cover_3.svg"),
}


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
    from django.templatetags.static import static

    from .models import Scenario
    from .session_views import practice_domain, scenario_is_open

    best = _best_by_scenario(user)
    rows = {row.slug: row for row in Scenario.objects.select_related("topic").order_by("slug")}
    # Interactive scenarios written for the new engine (not converted from one of the cards above).
    interactive_only = {}
    for extra in rows.values():
        if (extra.status == Scenario.PUBLISHED and "source" not in (extra.content or {})
                and scenario_is_open(extra, user)):
            interactive_only.setdefault(practice_domain(extra), []).append(extra)
    catalog = []
    for row in get_domain_competencies(user):
        art = _TOPIC_ART.get(row["slug"], _TOPIC_ART["osint"])
        preferred = choose_scenario(row["slug"], _recent_scenario_keys(user, row["slug"]))
        preferred_key = preferred["key"] if preferred else ""
        scenarios = []
        # An original whose row was unpublished or archived in the studio is hidden.
        originals = [s for s in scenarios_for_domain(row["slug"])
                     if getattr(rows.get(slug_for(s["key"])), "status", Scenario.PUBLISHED) == Scenario.PUBLISHED]
        for index, scenario in enumerate(originals, start=1):
            slug = slug_for(scenario["key"])
            # A row edited in the studio shows its own published text, not the original's.
            edited = rows[slug] if slug in rows and rows[slug].source == Scenario.STUDIO else None
            story = (edited.content.get("steps") or [{}])[0] if edited else {}
            scene = scenario.get("scene") or {}
            completed = scenario["key"] in best
            scenarios.append({
                "key": scenario["key"],
                "number": f"{index:02d}",
                "title": edited.title if edited else scenario["title"],
                "summary": story.get("intro", "") if edited else scenario.get("briefing", {}).get("summary", ""),
                "activity": scenario.get("activity_type") or "simulation",
                "activity_label": (scenario.get("activity_type") or "simulation").replace("_", " ").title(),
                "difficulty": scenario.get("difficulty") or "beginner",
                "difficulty_label": (scenario.get("difficulty") or "beginner").title(),
                "minutes": _SCENARIO_MINUTES.get(scenario.get("difficulty"), 15),
                "objective": story.get("desc", "") if edited else scenario.get("objective") or "",
                "completed": completed,
                "best": best.get(scenario["key"]) if completed else None,
                "preferred": scenario["key"] == preferred_key,
                "scene": {
                    "nodes": scene.get("nodes") or [],
                    "suspicious": scene.get("suspicious") or [],
                },
                # Detail panel: the console and its investigation steps (decisions stay hidden).
                "workspace": scenario.get("environment") or "",
                "severity": scenario.get("severity") or "",
                "tools": [step["label"] for step in (scenario.get("investigations") or {}).values()],
                "art": static(art[(index - 1) % 2]),
                "art_alt": "mission" if (index - 1) % 2 == 0 else "cover",
                "url": reverse("practice:session", args=[slug]),
            })
        for extra in interactive_only.get(row["slug"], []):
            index = len(scenarios) + 1
            story = (extra.content.get("steps") or [{}])[0]
            scenarios.append({
                "key": extra.slug,
                "number": f"{index:02d}",
                "title": extra.title,
                "summary": story.get("desc", ""),
                "activity": extra.kind,
                "activity_label": extra.get_kind_display(),
                "difficulty": extra.difficulty,
                "difficulty_label": extra.difficulty.title(),
                "minutes": extra.est_minutes,
                "objective": story.get("intro", ""),
                "completed": extra.slug in best,
                "best": best.get(extra.slug),
                "preferred": False,
                "scene": {"nodes": [], "suspicious": []},
                "workspace": "",
                "severity": "",
                "tools": [],
                "art": static(art[(index - 1) % 2]),
                "art_alt": "mission" if (index - 1) % 2 == 0 else "cover",
                "url": reverse("practice:session", args=[extra.slug]),
            })
        done = sum(1 for item in scenarios if item["completed"])
        catalog.append({
            "slug": row["slug"],
            "full_label": row["full_label"],
            "completed_count": done,
            "progress": round(done / len(scenarios) * 100) if scenarios else 0,
            "emoji": row["emoji"],
            "percent": row["percent"],
            "level": row["level"],
            "activity_label": row["activity_label"],
            "difficulty_label": row["difficulty_label"],
            "scenario_count": len(scenarios),
            "start_url": reverse("practice:start", args=[row["slug"]]),
            "scenarios": scenarios,
            "coming_soon": bool(row.get("coming_soon")),
        })
    return catalog


def _center_courses(catalog):
    """The eight active courses, in curriculum order, each with its practice topic (or none yet)."""
    from django.templatetags.static import static

    from courses.models import Course

    by_slug = {row["slug"]: row for row in catalog}
    courses = []
    for index, course in enumerate(Course.objects.active().order_by("order", "code"), start=1):
        topic = by_slug.get(_COURSE_PRACTICE_TOPIC.get(course.code, ""))
        cover = course.safe_thumbnail_url() or static(f"courses/covers/cover_{(index - 1) % 6 + 1}.svg")
        courses.append({
            "panel": f"course-{course.code}",
            "number": f"{index:02d}",
            "code": course.code,
            "title": course.title,
            "summary": course.short_description,
            "icon": _COURSE_ICONS.get(course.code, "book"),
            "cover": cover,
            "course_url": reverse("courses:detail", args=[course.code]),
            "topic": topic,
        })
    return courses


@login_required(login_url="/accounts/login/")
def practice_center(request):
    ctx = build_practice_center_context(request.user)
    catalog = _center_catalog(request.user)
    selected_slug = (ctx.get("recommendation") or {}).get("domain_slug") or "phishing"
    if request.GET.get("topic") in {row["slug"] for row in catalog if not row.get("coming_soon")}:
        selected_slug = request.GET["topic"]
    active_catalog = [row for row in catalog if not row.get("coming_soon")]
    selected = next((row for row in active_catalog if row["slug"] == selected_slug), active_catalog[0] if active_catalog else catalog[0])
    opening = next((s for s in selected["scenarios"] if s["preferred"]), selected["scenarios"][0])
    for row in ctx["domains"]:
        row["scenario_count"] = len(scenarios_for_domain(row["slug"]))
    active_catalog = [row for row in catalog if not row.get("coming_soon")]
    explored_count = sum(1 for row in active_catalog if row["percent"] > 0)
    overall_percent = round(sum(row["percent"] for row in active_catalog) / len(active_catalog)) if active_catalog else 0
    # Bookshelf layout: courses first, then practice topics that have no course of their own.
    courses = _center_courses(catalog)
    course_topics = {c["topic"]["slug"] for c in courses if c["topic"]}
    extra_topics = [row for row in catalog if row["slug"] not in course_topics]
    selected_panel = next(
        (c["panel"] for c in courses if c["topic"] and c["topic"]["slug"] == selected["slug"]),
        f"topic-{selected['slug']}",
    )
    available = [row for row in catalog if not row.get("coming_soon")]
    total_scenarios = sum(row["scenario_count"] for row in available)
    completed_scenarios = sum(row["completed_count"] for row in available)
    practice_xp = (
        PracticeSession.objects.filter(user=request.user, status="completed")
        .aggregate(total=Sum("xp_awarded"))["total"] or 0
    ) + (
        Attempt.objects.real().filter(user=request.user, finished_at__isnull=False)
        .aggregate(total=Sum("xp_awarded"))["total"] or 0
    )
    return render(request, "practice/center.html", {
        **ctx,
        "catalog": catalog,
        "selected_domain": selected,
        "opening": opening,
        "explored_count": explored_count,
        "overall_percent": overall_percent,
        "courses": courses,
        "extra_topics": extra_topics,
        "selected_panel": selected_panel,
        "total_scenarios": total_scenarios,
        "completed_scenarios": completed_scenarios,
        "scenario_percent": round(completed_scenarios / total_scenarios * 100) if total_scenarios else 0,
        "practice_xp": practice_xp,
    })


@login_required(login_url="/accounts/login/")
def domain_detail(request, domain):
    """/practice/<slug>/: an interactive scenario, or (for a topic slug) the Practice Center on that topic."""
    if not DOMAIN_BY_SLUG.get(domain):
        from .session_views import session_page
        return session_page(request, domain)
    return redirect(f"{reverse('practice:center')}?topic={domain}")


def _session_redirect(scenario_key):
    """The interactive session for an original scenario key (every scenario runs there now)."""
    from .models import Scenario
    slug = slug_for(scenario_key)
    if not Scenario.objects.published().filter(slug=slug).exists():
        raise Http404("This scenario has not been converted yet. Run manage.py convert_scenarios.")
    return redirect("practice:session", slug=slug)


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
        return redirect(f"{reverse('practice:center')}?topic={domain}")

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

    return _session_redirect(scenario["key"])


# The old step-by-step console is retired: its URLs send unfinished sessions to the same
# scenario in the interactive engine. Finished sessions keep their result page (history).
@login_required(login_url="/accounts/login/")
def play_session(request, session_id):
    session = get_object_or_404(PracticeSession, pk=session_id, user=request.user)
    if session.status == "completed":
        return redirect("practice:result", session_id=session.pk)
    return _session_redirect(session.scenario_key)


@login_required(login_url="/accounts/login/")
@require_POST
def open_console(request, session_id):
    return play_session(request, session_id)


@login_required(login_url="/accounts/login/")
@require_POST
def submit_decision(request, session_id):
    return play_session(request, session_id)


@login_required(login_url="/accounts/login/")
def practice_result(request, session_id):
    session = get_object_or_404(PracticeSession, pk=session_id, user=request.user)
    if (session.state or {}).get("engine") == "interactive":
        return redirect("practice:session", slug=session.state["slug"])
    if session.status != "completed":
        return _session_redirect(session.scenario_key)

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

    # Learning summary: every option explained, and what each piece of evidence showed.
    chosen = state.get("decision_key")
    quality_order = {"correct": 0, "poor": 1, "unsafe": 2}
    option_review = sorted(
        (
            {
                "label": option["label"],
                "quality": option.get("quality", "poor"),
                "title": option.get("consequence_title", ""),
                "explanation": option.get("consequence", ""),
                "chosen": key == chosen,
            }
            for key, option in (scenario.get("decisions") or {}).items()
        ),
        key=lambda row: quality_order.get(row["quality"], 3),
    )
    evidence_notes = [
        {"label": step["label"], "note": step["reveal"].get("feedback", ""), "found": key in revealed}
        for key, step in inv.items()
    ]
    # Suggest the next scenario in the same topic (one not completed yet, if any).
    done_keys = set(
        PracticeSession.objects.filter(user=request.user, domain=session.domain, status="completed")
        .values_list("scenario_key", flat=True)
    )
    siblings = [row for row in scenarios_for_domain(session.domain) if row["key"] != scenario["key"]]
    next_scenario = next((row for row in siblings if row["key"] not in done_keys), siblings[0] if siblings else None)

    return render(request, "practice/result.html", {
        "option_review": option_review,
        "evidence_notes": evidence_notes,
        "takeaways": scenario.get("takeaways") or [],
        "next_scenario": next_scenario,
        "start_url": reverse("practice:start", args=[session.domain]),
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
    from .models import Scenario
    interactive_titles = dict(Scenario.objects.values_list("slug", "title"))
    for row in sessions:
        scenario = get_scenario(row.scenario_key)
        row.scenario_title = scenario["title"] if scenario else interactive_titles.get(row.scenario_key, row.scenario_key)
    return render(request, "practice/history.html", {"sessions": sessions})
