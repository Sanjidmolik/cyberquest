"""
games/views.py
------------------
quiz_game() serves set-based courses.

When an approved Question Bank pool has difficulty-classified questions,
CyberQuest builds a balanced attempt (difficulty × question_type).
Otherwise it falls back to whole QuestionSet selection / legacy QUIZ_GAMES.
"""

import random

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import GameAttempt, SET_COURSE_KEYS
from . import attempts as attempt_service
from .registry import game_by_key
from .quiz_data import QUIZ_GAMES
from .question_sets import pick_set_for_user, ensure_set_slots
from .xp import XP_PER_CORRECT_ANSWER, apply_xp_and_level_up
from courses.progress import course_for_game, is_game_unlocked

# Backward-compat alias — remove once no external code imports the old name.
_apply_xp_and_level_up = apply_xp_and_level_up


SESSION_QSET = "active_qset_{}"
SESSION_QIDS = "active_attempt_qids_{}"


def _require_course_completed(request, game_key):
    """A mission opens once the student has finished its course's book. Admins skip this."""
    if is_game_unlocked(request.user, game_key):
        return None
    course = course_for_game(game_key)
    if course is None:
        messages.error(request, "This mission unlocks when its course is published. Check back soon.")
    else:
        messages.error(request, f"Finish reading the {course.title} course to unlock this mission.")
    return redirect("courses:intro")


def _legacy_game_bundle(game_key):
    game = QUIZ_GAMES.get(game_key)
    if not game:
        return None
    from .game_config import get_game_question_config

    # A pool larger than one attempt gives a fresh random draw each time.
    pool = game["questions"]
    size = get_game_question_config(game_key)["attempt_size"]
    if len(pool) > size:
        questions = random.sample(pool, size)
        selected = [question["id"] for question in questions]
    else:
        questions, selected = pool, []
    return {
        "title": game["title"],
        "emoji": game["emoji"],
        "intro": game["intro"],
        "questions": questions,
        "question_set": None,
        "set_number": None,
        "set_version": None,
        "selected_question_ids": selected,
        "selection_mode": "legacy",
    }


def _balanced_game_bundle(request, game_key):
    """Build an attempt from approved bank pool using difficulty × type plan."""
    from question_bank.services.selection import (
        SelectionShortageError,
        latest_approved_bank,
        load_questions_by_ids,
        pool_supports_balanced_selection,
        select_questions_for_attempt,
    )

    if not pool_supports_balanced_selection(game_key):
        return None

    meta = QUIZ_GAMES.get(game_key) or {}
    session_key = SESSION_QIDS.format(game_key)
    existing_ids = request.session.get(session_key) or []

    if existing_ids:
        questions = load_questions_by_ids(existing_ids)
        if len(questions) == len(existing_ids):
            has_sim = any(q.question_type == "simulation" for q in questions)
            intro = meta.get("intro", f"Answer all {len(questions)} questions.")
            if has_sim:
                intro = meta.get(
                    "simulation_intro",
                    "Inspect each scenario carefully, then choose the best action.",
                )
            return {
                "title": meta.get("title", game_key),
                "emoji": meta.get("emoji", "🎮"),
                "intro": intro,
                "questions": [q.to_quiz_dict() for q in questions],
                "question_set": None,
                "set_number": None,
                "set_version": None,
                "set_type": "BALANCED",
                "set_title": "Balanced attempt",
                "selected_question_ids": existing_ids,
                "selection_mode": "balanced",
            }
        # Stale session ids — clear and rebuild
        request.session.pop(session_key, None)

    bank = latest_approved_bank(game_key)
    if not pool_supports_balanced_selection(game_key, bank):
        return None

    try:
        result = select_questions_for_attempt(game_key, bank=bank)
    except SelectionShortageError as exc:
        # Race: inventory changed after the satisfiability check.
        messages.error(request, str(exc))
        return {"_shortage": True}

    has_sim = any(q.question_type == "simulation" for q in result.questions)
    intro = meta.get("intro", f"Answer all {len(result.questions)} questions.")
    if has_sim:
        intro = meta.get(
            "simulation_intro",
            "Inspect each scenario carefully, then choose the best action.",
        )

    return {
        "title": meta.get("title", game_key),
        "emoji": meta.get("emoji", "🎮"),
        "intro": intro,
        "questions": result.to_quiz_dicts(),
        "question_set": None,
        "set_number": None,
        "set_version": None,
        "set_type": "BALANCED",
        "set_title": "Balanced attempt",
        "selected_question_ids": result.question_ids,
        "selection_mode": "balanced",
    }


def _set_game_bundle(user, game_key):
    # Legacy slots still ensured for fallback; approved bank sets take priority in pick_set_for_user.
    ensure_set_slots(game_key)
    meta = QUIZ_GAMES.get(game_key) or {}
    qset = pick_set_for_user(user, game_key)
    if not qset:
        legacy = _legacy_game_bundle(game_key)
        if legacy:
            return legacy
        return None

    if not qset.is_usable:
        legacy = _legacy_game_bundle(game_key)
        if legacy:
            return legacy
        return None

    questions = [q.to_quiz_dict() for q in qset.ordered_questions()]
    expected = qset.expected_question_count
    if len(questions) != expected:
        return None

    intro = meta.get("intro", f"Answer all {expected} questions.")
    if qset.set_type == qset.SET_TYPE_SIMULATION:
        intro = meta.get(
            "simulation_intro",
            "Inspect each scenario carefully, then choose the best action.",
        )

    return {
        "title": meta.get("title", qset.get_course_display()),
        "emoji": meta.get("emoji", "🎮"),
        "intro": intro,
        "questions": questions,
        "question_set": qset,
        "set_number": qset.set_number,
        "set_version": qset.version,
        "set_type": qset.set_type,
        "set_title": qset.title,
        "selected_question_ids": [q["id"] for q in questions],
        "selection_mode": "set",
    }


def _bundle_for_start(request, game_key, uses_sets):
    if uses_sets:
        bundle = _balanced_game_bundle(request, game_key)
        if bundle and bundle.get("_shortage"):
            return None
        if bundle is None:
            bundle = _set_game_bundle(request.user, game_key)
    else:
        bundle = _legacy_game_bundle(game_key)
    return bundle


def _pin_bundle_session(request, game_key, bundle):
    if not bundle:
        return
    if bundle.get("selection_mode") == "balanced" and bundle.get("selected_question_ids"):
        request.session[SESSION_QIDS.format(game_key)] = bundle["selected_question_ids"]
        request.session.pop(SESSION_QSET.format(game_key), None)
    elif bundle.get("question_set") is not None:
        request.session[SESSION_QSET.format(game_key)] = bundle["question_set"].pk
        request.session.pop(SESSION_QIDS.format(game_key), None)


def _clear_bundle_session(request, game_key):
    request.session.pop(SESSION_QSET.format(game_key), None)
    request.session.pop(SESSION_QIDS.format(game_key), None)


def _announce_finish(request, attempt):
    if attempt.xp_awarded:
        messages.success(request, f"+{attempt.xp_awarded} XP earned!")
    if getattr(attempt, "_leveled_up", False):
        messages.success(request, f"Level up! You're now Level {request.user.level}.")
    for badge in getattr(attempt, "_new_badges", []) or []:
        messages.success(request, f"🏆 New badge unlocked: {badge.icon_emoji} {badge.name}!")


def _nocache(response):
    """Play and result pages must not be reused with a stale countdown."""
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    return response


def _render_result(request, attempt):
    _announce_finish(request, attempt)
    _clear_bundle_session(request, attempt.game_key)
    payload = attempt_service.result_payload(attempt)
    if getattr(attempt, "_prior_finish", None) is not None:
        payload["already_completed"] = bool(attempt._prior_finish)
    return _nocache(render(request, "games/quiz_result.html", payload))


def _play_context(request, game_key, attempt):
    questions = attempt_service.questions_for_attempt(attempt)
    meta = QUIZ_GAMES.get(game_key) or {}
    bundle = {
        "title": meta.get("title", game_key),
        "emoji": meta.get("emoji", "🎮"),
        "intro": meta.get("intro", ""),
        "questions": questions,
        "set_number": attempt.set_number,
        "set_type": attempt.selection_mode,
        "set_title": "",
    }
    remaining_ms = 0
    if attempt.deadline_at:
        remaining_ms = max(0, int((attempt.deadline_at - timezone.now()).total_seconds() * 1000))
    return {
        "phase": "play",
        "game": bundle,
        "game_key": game_key,
        "questions": questions,
        "set_number": attempt.set_number,
        "theme": attempt_service.theme_for(game_key),
        "attempt": attempt,
        "deadline_iso": attempt.deadline_at.isoformat() if attempt.deadline_at else "",
        "server_now_iso": timezone.now().isoformat(),
        "remaining_ms": remaining_ms,
        "remaining_label": attempt_service.clock_label(remaining_ms),
        "limit_seconds": attempt_service.mission_seconds(),
        "saved_answers": attempt.answers or {},
    }


@login_required(login_url="/accounts/login/")
@require_http_methods(["GET", "HEAD", "POST"])
def quiz_game(request, game_key):
    meta = game_by_key(game_key)
    if meta and meta.get("coming_soon"):
        messages.info(request, f"{meta['card_name']} is coming soon and cannot be started yet.")
        return redirect("dashboard:home")

    blocked = _require_course_completed(request, game_key)
    if blocked:
        return blocked

    if game_key not in attempt_service.timed_game_keys():
        raise Http404("No such game.")

    uses_sets = game_key in SET_COURSE_KEYS

    if request.method == "GET" and request.GET.get("sync") == "1":
        attempt = attempt_service.active_attempt(request.user, game_key)
        if attempt is None or not attempt.deadline_at:
            return JsonResponse({"running": False, "remaining_ms": 0})
        remaining_ms = max(0, int((attempt.deadline_at - timezone.now()).total_seconds() * 1000))
        return _nocache(JsonResponse({
            "running": remaining_ms > 0,
            "remaining_ms": remaining_ms,
            "deadline": attempt.deadline_at.isoformat(),
            "server_now": timezone.now().isoformat(),
        }))

    if request.method == "POST":
        return _handle_quiz_post(request, game_key, uses_sets)

    attempt = attempt_service.active_attempt(request.user, game_key)
    if attempt is not None:
        if attempt.deadline_at and attempt.deadline_at <= timezone.now():
            try:
                finished = attempt_service.finish_attempt(
                    attempt, attempt.answers or {}, attempt_service.METHOD_EXPIRY,
                )
            except attempt_service.AttemptQuestionsMissing:
                messages.error(request, "This attempt's questions are no longer available.")
                return redirect("dashboard:home")
            return _render_result(request, finished)
        questions = attempt_service.questions_for_attempt(attempt)
        if not questions:
            messages.error(request, "Your attempt questions are no longer available. Please start again.")
            return redirect("dashboard:home")
        return _nocache(render(request, "games/quiz_game.html", _play_context(request, game_key, attempt)))

    quiz_meta = QUIZ_GAMES.get(game_key) or {
        "title": meta["name"] if meta else game_key,
        "emoji": meta["emoji"] if meta else "🎮",
        "intro": meta["description"] if meta else "",
    }
    from .game_config import get_game_question_config
    return _nocache(render(request, "games/quiz_game.html", {
        "phase": "intro",
        "game": quiz_meta,
        "game_key": game_key,
        "questions": [],
        "set_number": None,
        "theme": attempt_service.theme_for(game_key),
        "limit_seconds": attempt_service.mission_seconds(),
        "remaining_label": attempt_service.clock_label(attempt_service.mission_seconds() * 1000),
        "question_count": get_game_question_config(game_key)["attempt_size"],
    }))


def _handle_quiz_post(request, game_key, uses_sets):
    action = (request.POST.get("action") or "submit").strip()
    attempt = attempt_service.active_attempt(request.user, game_key)

    if action == "start":
        if attempt is not None and attempt.deadline_at and attempt.deadline_at > timezone.now():
            return redirect(request.path)
        bundle = _bundle_for_start(request, game_key, uses_sets)
        if bundle is None or not bundle.get("questions"):
            messages.error(request, "No ready question set is available for this mission yet.")
            return redirect("dashboard:home")
        _pin_bundle_session(request, game_key, bundle)
        try:
            started, outcome = attempt_service.start_attempt(request.user, game_key, bundle)
        except attempt_service.AttemptQuestionsMissing:
            messages.error(request, "This mission could not be started.")
            return redirect("dashboard:home")
        if outcome == "result":
            return _render_result(request, started)
        return redirect(request.path)

    if attempt is None:
        messages.error(request, "Start the mission before submitting answers.")
        return redirect(request.path)

    questions = attempt_service.questions_for_attempt(attempt)
    if not questions:
        messages.error(request, "Your attempt questions are no longer available. Please start again.")
        _clear_bundle_session(request, game_key)
        return redirect("dashboard:home")

    posted = attempt_service.answers_from_post(questions, request.POST)
    if action == "save":
        updated = attempt_service.remember_answers(attempt, posted)
        if updated.status != GameAttempt.STATUS_IN_PROGRESS:
            return JsonResponse({"ok": False, "expired": True})
        remaining_ms = 0
        if updated.deadline_at:
            remaining_ms = max(0, int((updated.deadline_at - timezone.now()).total_seconds() * 1000))
        return JsonResponse({"ok": True, "remaining_ms": remaining_ms})

    method = attempt_service.METHOD_TIMEOUT if action == "timeout" else attempt_service.METHOD_MANUAL
    try:
        finished = attempt_service.finish_attempt(attempt, posted, method)
    except attempt_service.AttemptQuestionsMissing:
        messages.error(request, "Your attempt questions are no longer available.")
        return redirect("dashboard:home")
    if finished.status == GameAttempt.STATUS_IN_PROGRESS:
        messages.error(request, "This attempt could not be submitted.")
        return redirect(request.path)
    return _render_result(request, finished)
