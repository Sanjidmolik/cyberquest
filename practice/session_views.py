"""Interactive practice sessions: the session page and its JSON API.

Answers never leave the server before the learner commits: `api_start` sends the
content with every answer key stripped, `api_answer` grades one step at a time, and
`api_complete` awards XP and badges through CyberQuest's existing functions.
"""

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from achievements.checks import check_and_award_badges
from games.xp import apply_xp_and_level_up

from .graders import GRADERS, InvalidAnswer, START_METERS, grade_branch, public_content
from .conversion import DOMAIN_BY_COURSE
from .models import Attempt, PracticeSession, Scenario, StepAnswer
from .scenarios import DOMAIN_BY_SLUG

LOGIN_URL = "/accounts/login/"
START_HEARTS = 3


def scenario_is_open(scenario, user):
    """Same rule as the Practice Center: open with its course, or with its practice topic while
    the course is Coming Soon (Cryptography and Steganography practice stay open; OSINT does not)."""
    course = scenario.topic
    if course.is_open_to(user):
        return True
    topic = DOMAIN_BY_SLUG.get(DOMAIN_BY_COURSE.get(course.code, ""))
    return bool(course.is_published and topic and not topic.get("coming_soon"))


def session_url(scenario):
    return reverse("practice:session", args=[scenario.slug])


def topic_label(scenario):
    siblings = list(Scenario.objects.published().filter(topic=scenario.topic).order_by("slug").values_list("slug", flat=True))
    if scenario.slug not in siblings:  # a draft in studio preview
        return f"{scenario.topic.title.upper()} · PREVIEW"
    return f"{scenario.topic.title.upper()} · SCENARIO {siblings.index(scenario.slug) + 1} OF {len(siblings)}"


def attempt_content(attempt):
    """The content this attempt is graded on: the version it started on, so publishing a new
    version never changes the answers under a learner who is mid-session."""
    return attempt.scenario.content_for_version(attempt.state.get("version"))


def _json_error(message, status):
    return JsonResponse({"error": message}, status=status)


def _body(request):
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _own_attempt(request, attempt_id):
    return (
        Attempt.objects.select_for_update()
        .select_related("scenario", "scenario__topic")
        .filter(pk=attempt_id, user=request.user)
        .first()
    )


@login_required(login_url=LOGIN_URL)
def session_page(request, slug):
    scenario = Scenario.objects.published().select_related("topic").filter(slug=slug).first()
    if scenario is None:
        raise Http404("Unknown practice scenario.")
    locked = not scenario_is_open(scenario, request.user)
    steps = scenario.content.get("steps") or []
    brief = public_content(steps[0]) if steps else {}
    return render(request, "practice/session.html", {
        "scenario": scenario,
        "brief": brief,
        "topic_label": topic_label(scenario),
        "locked": locked,
        "center_url": reverse("practice:center"),
        "session_config": {
            "slug": scenario.slug,
            "kind": scenario.kind,
            "title": scenario.title,
            "locked": locked,
            "hearts": START_HEARTS,
            "xp": request.user.xp,
            "csrf": get_token(request),
            "urls": {
                "start": reverse("practice:api_start"),
                "answer": reverse("practice:api_answer", args=[0]),
                "complete": reverse("practice:api_complete", args=[0]),
                "center": reverse("practice:center"),
                "replay": session_url(scenario),
            },
        },
    })


@login_required(login_url=LOGIN_URL)
@require_POST
def api_start(request):
    data = _body(request)
    slug = data.get("scenario") if data else None
    scenario = (Scenario.objects.published().select_related("topic").filter(slug=slug).first()
                if isinstance(slug, str) else None)
    if scenario is None:
        return _json_error("Unknown scenario.", 404)
    if not scenario_is_open(scenario, request.user):
        return _json_error("This scenario is not open yet.", 403)
    attempt = Attempt.objects.create(
        user=request.user, scenario=scenario, hearts=START_HEARTS,
        state={"version": scenario.version},
    )
    return JsonResponse({
        "attempt_id": attempt.pk,
        "kind": scenario.kind,
        "hearts": attempt.hearts,
        "content": public_content(scenario.content),
    }, status=201)


@login_required(login_url=LOGIN_URL)
@require_POST
def api_answer(request, attempt_id):
    data = _body(request)
    if data is None:
        return _json_error("Send a JSON body.", 400)
    with transaction.atomic():
        attempt = _own_attempt(request, attempt_id)
        if attempt is None:
            return _json_error("Attempt not found.", 404)
        if attempt.finished_at:
            return _json_error("This attempt is already finished.", 409)
        steps = attempt_content(attempt)["steps"]
        step_no = data.get("step")
        if isinstance(step_no, bool) or not isinstance(step_no, int) or not 0 <= step_no < len(steps):
            return _json_error("Unknown step.", 400)
        step = steps[step_no]
        kind = step["type"]
        if kind == "story":
            return _json_error("The briefing has nothing to answer.", 400)
        answer = data.get("answer")
        time_ms = data.get("time_ms")
        time_ms = max(0, min(int(time_ms), 86_400_000)) if isinstance(time_ms, (int, float)) and not isinstance(time_ms, bool) else 0
        confidence = data.get("confidence") if isinstance(data.get("confidence"), str) else ""
        record = {"attempt": attempt, "step_index": step_no, "time_ms": time_ms, "confidence": confidence[:12]}

        if kind == "branch":
            try:
                response, branch_state = grade_branch(step, answer, dict(attempt.state.get("branch") or {}))
            except InvalidAnswer as exc:
                return _json_error(str(exc), 400)
            attempt.state = {**attempt.state, "branch": branch_state}
            attempt.save(update_fields=["state"])
            StepAnswer.objects.create(answer=answer, correct=response["correct"], **record)
            return JsonResponse(response)

        if attempt.answers.filter(step_index=step_no).exists():
            return _json_error("This step is already answered.", 409)

        if kind == "concept_cards":
            StepAnswer.objects.create(answer=answer if answer is not None else "seen", correct=None, **record)
            return JsonResponse({"correct": None, "hearts": attempt.hearts})

        if isinstance(answer, dict) and answer.get("skipped") is True:
            # Skipping counts as a miss for accuracy but never costs a heart.
            StepAnswer.objects.create(answer={"skipped": True}, correct=False, **record)
            return JsonResponse({"correct": False, "skipped": True, "hearts": attempt.hearts})

        try:
            result = GRADERS[kind](step, answer)
        except InvalidAnswer as exc:
            return _json_error(str(exc), 400)
        if not result["correct"] and attempt.hearts:
            attempt.hearts -= 1
            attempt.save(update_fields=["hearts"])
        StepAnswer.objects.create(answer=answer, correct=result["correct"], **record)
        return JsonResponse({**result, "hearts": attempt.hearts})


@login_required(login_url=LOGIN_URL)
@require_POST
def api_complete(request, attempt_id):
    with transaction.atomic():
        attempt = _own_attempt(request, attempt_id)
        if attempt is None:
            return _json_error("Attempt not found.", 404)
        if attempt.finished_at:
            return JsonResponse(attempt.state.get("results") or {})

        scenario = attempt.scenario
        content = attempt_content(attempt)
        steps = content["steps"]
        answers = list(attempt.answers.all())
        answered = {a.step_index for a in answers}
        branch = attempt.state.get("branch") or {}
        missing = [
            i for i, step in enumerate(steps)
            if step["type"] != "story"
            and (not branch.get("ending") if step["type"] == "branch" else i not in answered)
        ]
        if missing:
            return JsonResponse({"error": "Finish every step first.", "missing": missing}, status=400)

        results = {"kind": scenario.kind, "debrief": content.get("debrief") or {}}
        if scenario.kind == "choice":
            branch_step = next(s for s in steps if s["type"] == "branch")
            picks = branch.get("picks") or []
            good = picks.count("good")
            accuracy = round(good / len(branch_step["scenes"]) * 100)
            ending = branch_step["endings"][branch["ending"]]
            outcome = branch["ending"]
            results.update({
                "good_calls": good, "total_calls": len(branch_step["scenes"]), "picks": picks,
                "meters": branch.get("meters") or dict(START_METERS),
                "ending": {"key": outcome, **ending},
            })
        else:
            graded = [a.correct for a in answers if a.correct is not None]
            accuracy = round(sum(graded) / len(graded) * 100) if graded else 100
            outcome = "completed"

        now = timezone.now()
        attempt.finished_at = now
        attempt.score = accuracy
        attempt.outcome = outcome
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        if attempt.is_preview:
            # Studio preview: graded and shown like a real run, but nothing is awarded or recorded.
            leveled, badges = False, []
            attempt.save(update_fields=["finished_at", "score", "outcome"])
        else:
            leveled = apply_xp_and_level_up(user, scenario.xp_reward)
            attempt.xp_awarded = scenario.xp_reward
            # Saved as finished before badges and skill progress are counted, so this attempt counts.
            attempt.save(update_fields=["finished_at", "score", "outcome", "xp_awarded"])
            _record_practice_session(attempt, now)
            badges = check_and_award_badges(user)

        seconds = int((now - attempt.started_at).total_seconds())
        results.update({
            "xp": attempt.xp_awarded,
            "accuracy": accuracy,
            "hearts": attempt.hearts,
            "time": f"{seconds // 60}:{seconds % 60:02d}",
            "time_sec": seconds,
            "outcome": outcome,
            "badges": [{"name": b.name, "description": b.description, "icon": b.icon_emoji} for b in badges],
            "level": {
                "level": user.level, "xp": user.xp, "leveled_up": leveled,
                "into": user.xp % 100, "to_next": 100 - user.xp % 100,
            },
            "competency": _competency(user, scenario),
            "next": _next_scenario(user, scenario),
        })
        attempt.state = {**attempt.state, "results": results}
        attempt.save(update_fields=["state"])
    return JsonResponse(results)


def practice_domain(scenario):
    """The original practice topic a scenario belongs to (Cyber DNA, history and badges use it)."""
    source = (scenario.content or {}).get("source") or {}
    return source.get("domain") or DOMAIN_BY_COURSE.get(scenario.topic.code, "")


def _record_practice_session(attempt, finished_at):
    """Keep one completed PracticeSession per finished attempt, so competency, Cyber DNA,
    recommendations, history, analytics and the practice badges keep counting practice.
    XP lives on the attempt, so this row records 0 XP."""
    scenario = attempt.scenario
    domain = practice_domain(scenario)
    if not domain:
        return
    source_key = ((scenario.content or {}).get("source") or {}).get("key") or scenario.slug
    PracticeSession.objects.create(
        user_id=attempt.user_id,
        domain=domain,
        activity_type=scenario.kind if scenario.kind in ("simulation", "incident") else "simulation",
        scenario_key=source_key,
        difficulty=scenario.difficulty if scenario.difficulty in ("beginner", "intermediate", "advanced") else "beginner",
        score=attempt.score,
        max_score=100,
        status="completed",
        completed_at=finished_at,
        xp_awarded=0,
        result_summary=(attempt_content(attempt).get("debrief") or {}).get("sub", ""),
        state={"engine": "interactive", "attempt_id": attempt.pk, "slug": scenario.slug},
    )


def _completed_ids(user):
    return set(
        Attempt.objects.filter(user=user, finished_at__isnull=False, is_preview=False)
        .values_list("scenario_id", flat=True)
    )


def _competency(user, scenario):
    course_ids = list(Scenario.objects.published().filter(topic=scenario.topic).values_list("pk", flat=True))
    done = len(_completed_ids(user) & set(course_ids))
    return {
        "course": scenario.topic.title,
        "done": done,
        "total": len(course_ids),
        "percent": round(done / len(course_ids) * 100) if course_ids else 0,
    }


def _next_scenario(user, scenario):
    """Next open scenario: an unplayed one in the same course first, then in any course."""
    done = _completed_ids(user)
    others = [
        s for s in Scenario.objects.published().select_related("topic").exclude(pk=scenario.pk)
        if scenario_is_open(s, user)
    ]
    others.sort(key=lambda s: (s.topic_id != scenario.topic_id, s.pk in done, s.topic.order, s.slug))
    if not others:
        return None
    nxt = others[0]
    return {
        "title": nxt.title,
        "url": session_url(nxt),
        "kind": nxt.get_kind_display(),
        "difficulty": nxt.difficulty.title(),
        "minutes": nxt.est_minutes,
    }
