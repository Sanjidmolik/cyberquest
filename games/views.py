"""
games/views.py
------------------
quiz_game() serves set-based courses.

When an approved Question Bank pool has difficulty-classified questions,
CyberQuest builds a balanced attempt (difficulty × question_type).
Otherwise it falls back to whole QuestionSet selection / legacy QUIZ_GAMES.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import Http404

from .models import GameAttempt, SET_COURSE_KEYS
from .registry import game_by_key
from .quiz_data import QUIZ_GAMES
from .question_sets import pick_set_for_user, ensure_set_slots
from courses.progress import has_completed_all_courses
from achievements.checks import check_and_award_badges

XP_PER_CORRECT_ANSWER = 20

SESSION_QSET = "active_qset_{}"
SESSION_QIDS = "active_attempt_qids_{}"


def _require_course_completed(request):
    if not has_completed_all_courses(request.user):
        messages.error(request, "Please complete the course introduction first.")
        return redirect("courses:intro")
    return None


def _apply_xp_and_level_up(user, xp_awarded):
    old_level = user.level
    user.xp += xp_awarded
    user.level = (user.xp // 100) + 1
    user.save(update_fields=["xp", "level"])
    return user.level > old_level


def _legacy_game_bundle(game_key):
    game = QUIZ_GAMES.get(game_key)
    if not game:
        return None
    return {
        "title": game["title"],
        "emoji": game["emoji"],
        "intro": game["intro"],
        "questions": game["questions"],
        "question_set": None,
        "set_number": None,
        "set_version": None,
        "selected_question_ids": [],
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


@login_required(login_url="/accounts/login/")
def quiz_game(request, game_key):
    meta = game_by_key(game_key)
    if meta and meta.get("coming_soon"):
        messages.info(request, "OSINT is coming soon and cannot be started yet.")
        return redirect("dashboard:home")

    blocked = _require_course_completed(request)
    if blocked:
        return blocked

    uses_sets = game_key in SET_COURSE_KEYS

    if request.method == "POST":
        return _grade_submission(request, game_key, uses_sets)

    if uses_sets:
        bundle = _balanced_game_bundle(request, game_key)
        if bundle and bundle.get("_shortage"):
            return redirect("dashboard:home")
        if bundle is None:
            bundle = _set_game_bundle(request.user, game_key)
    else:
        bundle = _legacy_game_bundle(game_key)

    if bundle is None:
        raise Http404("No such game.")

    # Persist selection for refresh stability
    if bundle.get("selection_mode") == "balanced" and bundle.get("selected_question_ids"):
        request.session[SESSION_QIDS.format(game_key)] = bundle["selected_question_ids"]
        request.session.pop(SESSION_QSET.format(game_key), None)
    elif bundle.get("question_set") is not None:
        request.session[SESSION_QSET.format(game_key)] = bundle["question_set"].pk
        request.session.pop(SESSION_QIDS.format(game_key), None)

    return render(request, "games/quiz_game.html", {
        "game": bundle,
        "game_key": game_key,
        "questions": bundle["questions"],
        "set_number": bundle["set_number"],
    })


def _grade_submission(request, game_key, uses_sets):
    from .models import QuestionSet
    from question_bank.services.selection import load_questions_by_ids

    questions = []
    qset = None
    set_number = None
    set_version = None
    selected_ids: list[int] = []

    if uses_sets:
        qids = request.session.get(SESSION_QIDS.format(game_key)) or []
        if qids:
            loaded = load_questions_by_ids(qids)
            if len(loaded) == len(qids):
                questions = [q.to_quiz_dict() for q in loaded]
                selected_ids = list(qids)
            else:
                messages.error(
                    request,
                    "Your attempt questions are no longer available. Please start again.",
                )
                request.session.pop(SESSION_QIDS.format(game_key), None)
                return redirect("dashboard:home")
        else:
            set_id = request.session.get(SESSION_QSET.format(game_key))
            if set_id:
                qset = QuestionSet.objects.filter(pk=set_id, course=game_key).first()
            if qset and qset.is_usable:
                questions = [q.to_quiz_dict() for q in qset.ordered_questions()]
                set_number = qset.set_number
                set_version = qset.version
                selected_ids = [q["id"] for q in questions]
            else:
                bundle = _balanced_game_bundle(request, game_key)
                if bundle and bundle.get("_shortage"):
                    return redirect("dashboard:home")
                if not bundle:
                    bundle = _set_game_bundle(request.user, game_key)
                if not bundle or not bundle["questions"]:
                    messages.error(
                        request,
                        "No ready question set is available for this course yet.",
                    )
                    return redirect("dashboard:home")
                questions = bundle["questions"]
                qset = bundle["question_set"]
                set_number = bundle["set_number"]
                set_version = bundle["set_version"]
                selected_ids = bundle.get("selected_question_ids") or []
    else:
        legacy = _legacy_game_bundle(game_key)
        if not legacy:
            raise Http404("No such game.")
        questions = legacy["questions"]

    score = 0
    results = []
    for question in questions:
        submitted = request.POST.get(f"question_{question['id']}")
        try:
            submitted_index = int(submitted)
        except (TypeError, ValueError):
            submitted_index = -1

        correct = submitted_index == question["correct_index"]
        if correct:
            score += 1

        selected_answer = (
            question["options"][submitted_index]
            if 0 <= submitted_index < len(question["options"])
            else "— no answer —"
        )
        correct_answer = question["options"][question["correct_index"]]
        results.append({
            "prompt": question["prompt"],
            "correct": correct,
            "selected_answer": selected_answer,
            "correct_answer": correct_answer,
            "explanation": question.get("explanation", ""),
            "correct_feedback": question.get("correct_feedback", "Correct!"),
            "wrong_feedback": question.get("wrong_feedback", "Incorrect."),
        })

    total = len(questions)
    already_completed = GameAttempt.objects.filter(user=request.user, game_key=game_key).exists()

    xp_awarded = 0
    leveled_up = False
    if not already_completed:
        xp_awarded = score * XP_PER_CORRECT_ANSWER
        leveled_up = _apply_xp_and_level_up(request.user, xp_awarded)

    GameAttempt.objects.create(
        user=request.user,
        game_key=game_key,
        score=score,
        total_questions=total,
        xp_awarded=xp_awarded,
        question_set=qset,
        set_number=set_number,
        set_version=set_version,
        selected_question_ids=selected_ids,
    )

    request.session.pop(SESSION_QSET.format(game_key), None)
    request.session.pop(SESSION_QIDS.format(game_key), None)

    if xp_awarded:
        messages.success(request, f"+{xp_awarded} XP earned!")
    if leveled_up:
        messages.success(request, f"Level up! You're now Level {request.user.level}.")

    for badge in check_and_award_badges(request.user):
        messages.success(request, f"🏆 New badge unlocked: {badge.icon_emoji} {badge.name}!")

    meta = QUIZ_GAMES.get(game_key) or {"title": game_key, "emoji": "🎮"}
    return render(request, "games/quiz_result.html", {
        "game": meta,
        "score": score,
        "total": total,
        "percent": round(score / total * 100) if total else 0,
        "results": results,
        "xp_awarded": xp_awarded,
        "already_completed": already_completed,
        "set_number": set_number,
    })
