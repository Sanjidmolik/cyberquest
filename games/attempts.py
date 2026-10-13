"""Server-side mission attempts.

The browser draws the clock. This module owns the deadline, grading, and
the single finish of each attempt.
"""

from __future__ import annotations

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import GameAttempt
from .quiz_data import QUIZ_GAMES
from .registry import playable_games

METHOD_MANUAL = "manual"
METHOD_TIMEOUT = "timeout"
METHOD_EXPIRY = "expiry"

MISSION_THEMES = {
    "phishing_simulator": {
        "slug": "phishing",
        "number": "MISSION 1",
        "title": "PHISHING",
        "tip": "Official organizations usually do not ask for sensitive information through email.",
        "art_alt": "Comic scene of a learner inspecting a suspicious email",
        "lines": {
            "mastered": ("SHARP EYE!", "You spotted the phishing clues in this mission."),
            "partial": ("GOOD WORK!", "Review the messages you missed before the next try."),
            "zero": ("LOOK AGAIN", "Use the review to see which messages were suspicious."),
            "timeout": ("TIME'S UP!", "Time's up. Unanswered questions are marked incorrect."),
            "repeat": ("ALREADY FINISHED", "This attempt was already completed. No new XP was awarded."),
        },
    },
    "password_cracker": {
        "slug": "password",
        "number": "MISSION 2",
        "title": "PASSWORD CRACKER",
        "tip": "A stronger password mixes length with uppercase, lowercase, numbers, and symbols.",
        "art_alt": "Comic scene of a learner with a lock and a shield",
        "lines": {
            "mastered": ("GREAT EFFORT!", "You worked through the password ideas in this mission."),
            "partial": ("SOLID TRY!", "Review the password questions you missed."),
            "zero": ("KEEP TRAINING", "The review shows what makes a password stronger."),
            "timeout": ("TIME'S UP!", "Time's up. Unanswered questions are marked incorrect."),
            "repeat": ("ALREADY FINISHED", "This attempt was already completed. No new XP was awarded."),
        },
    },
    "network_defense": {
        "slug": "network",
        "number": "MISSION 3",
        "title": "NETWORK DEFENCE",
        "tip": "Look for unusual traffic, unknown addresses, and abnormal behavior in the logs.",
        "art_alt": "Comic scene of a learner watching a firewall and network map",
        "lines": {
            "mastered": ("WELL DONE!", "You read the network clues in this mission."),
            "partial": ("GOOD DEFENCE", "Review the traffic you misread, then try again."),
            "zero": ("BACK TO THE LOGS", "The review shows which traffic needed attention."),
            "timeout": ("TIME'S UP!", "Time's up. Unanswered questions are marked incorrect."),
            "repeat": ("ALREADY FINISHED", "This attempt was already completed. No new XP was awarded."),
        },
    },
    "cryptography": {
        "slug": "crypto",
        "number": "MISSION 4",
        "title": "CRYPTOGRAPHY",
        "tip": "Look for patterns, common keys, and the difference between encoding and encryption.",
        "art_alt": "Comic scene of a learner with a cipher wheel and a key",
        "lines": {
            "mastered": ("CODE BROKEN!", "You unlocked the cryptography ideas in this mission."),
            "partial": ("ALMOST THERE", "Review the ciphers you missed before trying again."),
            "zero": ("KEEP DECODING", "The review shows the key ideas from this mission."),
            "timeout": ("TIME'S UP!", "Time's up. Unanswered questions are marked incorrect."),
            "repeat": ("ALREADY FINISHED", "This attempt was already completed. No new XP was awarded."),
        },
    },
    "steganography": {
        "slug": "stego",
        "number": "MISSION 5",
        "title": "STEGANOGRAPHY",
        "tip": "Check for unusual patterns, metadata, or hidden content inside the file.",
        "art_alt": "Comic scene of a learner searching a picture for hidden details",
        "lines": {
            "mastered": ("SHARP EYE!", "You found the hidden-detail clues in this mission."),
            "partial": ("GOOD SEARCH", "Review the images and clues you missed."),
            "zero": ("LOOK CLOSER", "The review shows where the hidden details were."),
            "timeout": ("TIME'S UP!", "Time's up. Unanswered questions are marked incorrect."),
            "repeat": ("ALREADY FINISHED", "This attempt was already completed. No new XP was awarded."),
        },
    },
}

GAME_URL_NAMES = {
    "phishing_simulator": "games:phishing_simulator",
    "password_cracker": "games:password_cracker",
    "network_defense": "games:network_defense",
    "cryptography": "games:cryptography",
    "steganography": "games:steganography",
}


def mission_seconds() -> int:
    return int(getattr(settings, "MISSION_TIME_LIMIT_SECONDS", 60))


def clock_label(remaining_ms: int) -> str:
    """Digital readout shared by the server-rendered clock and the browser."""
    total_ms = max(0, int(remaining_ms))
    seconds = min(3600, (total_ms + 999) // 1000)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def qualifying_percent() -> int:
    return int(getattr(settings, "MISSION_QUALIFYING_SCORE_PERCENT", 80))


class AttemptQuestionsMissing(Exception):
    pass


def timed_game_keys() -> frozenset:
    return frozenset(game["key"] for game in playable_games())


def theme_for(game_key: str) -> dict:
    return MISSION_THEMES.get(game_key) or {
        "slug": "phishing",
        "number": "MISSION",
        "title": game_key.replace("_", " ").upper(),
        "tip": "",
    }


def active_attempt(user, game_key):
    return (
        GameAttempt.objects.filter(
            user=user,
            game_key=game_key,
            status=GameAttempt.STATUS_IN_PROGRESS,
        )
        .order_by("-id")
        .first()
    )


def questions_for_attempt(attempt: GameAttempt) -> list[dict]:
    ids = list(attempt.selected_question_ids or [])
    if attempt.selection_mode == "legacy" or attempt.game_key not in _set_courses():
        legacy = (QUIZ_GAMES.get(attempt.game_key) or {}).get("questions") or []
        by_id = {question["id"]: question for question in legacy}
        if ids:
            return [by_id[item] for item in ids if item in by_id]
        return list(legacy)

    from question_bank.services.selection import load_questions_by_ids

    loaded = load_questions_by_ids(ids)
    if len(loaded) != len(ids):
        return []
    return [question.to_quiz_dict() for question in loaded]


def _set_courses():
    from .models import SET_COURSE_KEYS
    return set(SET_COURSE_KEYS)


def answers_from_post(questions, post) -> dict:
    found = {}
    for question in questions:
        raw = post.get(f"question_{question['id']}")
        if raw is None or raw == "":
            continue
        try:
            found[str(question["id"])] = int(raw)
        except (TypeError, ValueError):
            continue
    return found


def grade_questions(questions, answer_map) -> tuple[int, list[dict]]:
    score = 0
    results = []
    for question in questions:
        submitted_index = answer_map.get(str(question["id"]), -1)
        try:
            submitted_index = int(submitted_index)
        except (TypeError, ValueError):
            submitted_index = -1
        answered = 0 <= submitted_index < len(question["options"])
        correct = answered and submitted_index == question["correct_index"]
        if correct:
            score += 1
        options = question["options"]
        selected_answer = options[submitted_index] if answered else "— no answer —"
        if correct:
            status = "correct"
        elif answered:
            status = "incorrect"
        else:
            status = "unanswered"
        results.append({
            "prompt": question["prompt"],
            "correct": correct,
            "status": status,
            "selected_answer": selected_answer,
            "correct_answer": options[question["correct_index"]],
            "explanation": question.get("explanation", ""),
            "correct_feedback": question.get("correct_feedback", "Correct!"),
            "wrong_feedback": question.get("wrong_feedback", "Incorrect."),
        })
    return score, results


def start_attempt(user, game_key, bundle) -> tuple[GameAttempt, str]:
    """Return (attempt, outcome) where outcome is play, result, or created.

    An existing live attempt is reused. An expired one is finalized first.
    """
    now = timezone.now()
    with transaction.atomic():
        existing = (
            GameAttempt.objects.select_for_update()
            .filter(user=user, game_key=game_key, status=GameAttempt.STATUS_IN_PROGRESS)
            .order_by("-id")
            .first()
        )
        if existing is not None:
            if existing.deadline_at and existing.deadline_at <= now:
                _finish_locked(existing, existing.answers or {}, METHOD_EXPIRY, now)
                return existing, "result"
            return existing, "play"

        deadline = now + timezone.timedelta(seconds=mission_seconds())
        attempt = GameAttempt(
            user=user,
            game_key=game_key,
            score=0,
            total_questions=len(bundle["questions"]),
            xp_awarded=0,
            status=GameAttempt.STATUS_IN_PROGRESS,
            started_at=now,
            deadline_at=deadline,
            completed_at=None,
            question_set=bundle.get("question_set"),
            set_number=bundle.get("set_number"),
            set_version=bundle.get("set_version"),
            selected_question_ids=list(bundle.get("selected_question_ids") or []),
            selection_mode=bundle.get("selection_mode") or "",
            answers={},
        )
        try:
            with transaction.atomic():
                attempt.save()
        except IntegrityError:
            existing = active_attempt(user, game_key)
            if existing is None:
                raise
            return existing, "play"
        return attempt, "created"


def remember_answers(attempt: GameAttempt, answer_map: dict) -> GameAttempt:
    now = timezone.now()
    with transaction.atomic():
        locked = (
            GameAttempt.objects.select_for_update()
            .filter(pk=attempt.pk, status=GameAttempt.STATUS_IN_PROGRESS)
            .first()
        )
        if locked is None:
            return attempt
        if locked.deadline_at and locked.deadline_at <= now:
            return locked
        merged = dict(locked.answers or {})
        merged.update(answer_map)
        locked.answers = merged
        locked.save(update_fields=["answers"])
        return locked


def finish_attempt(attempt: GameAttempt, answer_map: dict, method: str) -> GameAttempt:
    now = timezone.now()
    with transaction.atomic():
        locked = (
            GameAttempt.objects.select_for_update()
            .filter(pk=attempt.pk)
            .first()
        )
        if locked is None:
            return attempt
        if locked.status != GameAttempt.STATUS_IN_PROGRESS:
            return locked
        stored = dict(locked.answers or {})
        stored.update(answer_map or {})
        _finish_locked(locked, stored, method, now)
        return locked


def finalize_expired_attempts(user=None, limit=100) -> int:
    """Idempotently close attempts whose deadline has passed."""
    now = timezone.now()
    qs = GameAttempt.objects.filter(
        status=GameAttempt.STATUS_IN_PROGRESS,
        deadline_at__lte=now,
    )
    if user is not None:
        qs = qs.filter(user=user)
    count = 0
    for attempt_id in qs.values_list("pk", flat=True)[:limit]:
        attempt = GameAttempt.objects.filter(pk=attempt_id).first()
        if attempt is None:
            continue
        try:
            finish_attempt(attempt, attempt.answers or {}, METHOD_EXPIRY)
        except AttemptQuestionsMissing:
            continue
        count += 1
    return count


def _finish_locked(attempt: GameAttempt, answer_map: dict, method: str, now) -> None:
    """Grade a row that is already locked and still in progress."""
    if attempt.status != GameAttempt.STATUS_IN_PROGRESS:
        return
    questions = questions_for_attempt(attempt)
    if not questions:
        raise AttemptQuestionsMissing(attempt.game_key)
    score, results = grade_questions(questions, answer_map)
    deadline = attempt.deadline_at or now
    started = attempt.started_at or now
    timed_out = method == METHOD_EXPIRY or now > deadline
    if timed_out:
        elapsed = mission_seconds()
        remaining = 0
        submission = METHOD_EXPIRY if method == METHOD_EXPIRY else METHOD_TIMEOUT
    else:
        elapsed = int(max(0, (now - started).total_seconds()))
        elapsed = min(elapsed, mission_seconds())
        remaining = int(max(0, (deadline - now).total_seconds()))
        submission = METHOD_MANUAL

    prior = GameAttempt.objects.filter(
        user_id=attempt.user_id,
        game_key=attempt.game_key,
        status__in=[GameAttempt.STATUS_COMPLETED, GameAttempt.STATUS_TIMED_OUT],
    ).exclude(pk=attempt.pk).exists()

    attempt.score = score
    attempt.total_questions = len(questions)
    attempt.answers = {str(key): int(value) for key, value in answer_map.items()}
    attempt.elapsed_seconds = elapsed
    attempt.time_remaining_seconds = remaining
    attempt.submission_method = submission
    attempt.status = (
        GameAttempt.STATUS_TIMED_OUT if timed_out else GameAttempt.STATUS_COMPLETED
    )
    attempt.completed_at = now
    xp_awarded = 0
    if not prior:
        from .views import XP_PER_CORRECT_ANSWER, _apply_xp_and_level_up
        xp_awarded = score * XP_PER_CORRECT_ANSWER
    attempt.xp_awarded = xp_awarded
    attempt.save()

    user = attempt.user
    leveled_up = False
    if xp_awarded:
        leveled_up = _apply_xp_and_level_up(user, xp_awarded)
    attempt._result_cache = results
    attempt._leveled_up = leveled_up
    attempt._prior_finish = prior

    from achievements.checks import check_and_award_badges
    attempt._new_badges = check_and_award_badges(user)


def _clock_stamp(seconds) -> str:
    total = max(0, int(seconds or 0))
    return f"{total // 60:02d}:{total % 60:02d}"


def _result_line(theme: dict, *, score: int, total: int, timed_out: bool, already: bool):
    lines = theme.get("lines") or {}
    if already:
        key = "repeat"
    elif timed_out:
        key = "timeout"
    elif total and score >= total:
        key = "mastered"
    elif score <= 0:
        key = "zero"
    else:
        key = "partial"
    headline, detail = lines.get(key) or ("MISSION COMPLETE", "Review your answers below.")
    return key, headline, detail


def result_payload(attempt: GameAttempt) -> dict:
    from django.urls import reverse

    questions = questions_for_attempt(attempt)
    answer_map = attempt.answers or {}
    score, results = grade_questions(questions, answer_map)
    meta = QUIZ_GAMES.get(attempt.game_key) or {"title": attempt.game_key, "emoji": "🎮"}
    total = attempt.total_questions or len(questions)
    final_score = attempt.score if attempt.is_finished else score
    timed_out = attempt.status == GameAttempt.STATUS_TIMED_OUT
    already = _had_prior(attempt)
    theme = theme_for(attempt.game_key)
    outcome, headline, detail = _result_line(
        theme, score=final_score, total=total, timed_out=timed_out, already=already,
    )
    if results:
        incorrect = sum(1 for item in results if not item["correct"])
        unanswered = sum(1 for item in results if item.get("status") == "unanswered")
    else:
        incorrect = max(0, total - final_score)
        unanswered = 0
    url_name = GAME_URL_NAMES.get(attempt.game_key)
    return {
        "game": meta,
        "game_key": attempt.game_key,
        "theme": theme,
        "score": final_score,
        "total": total,
        "percent": round(final_score / total * 100) if total else 0,
        "results": results,
        "incorrect_count": incorrect,
        "unanswered_count": unanswered,
        "xp_awarded": attempt.xp_awarded,
        "already_completed": already,
        "outcome": outcome,
        "speech_headline": headline,
        "speech_detail": detail,
        "set_number": attempt.set_number,
        "retry_url": reverse(url_name) if url_name else "",
        "missions_url": reverse("dashboard:home") + "#active-missions",
        "learn_url": reverse("courses:intro"),
        "timing": {
            "elapsed_seconds": attempt.elapsed_seconds,
            "elapsed_label": (
                _clock_stamp(attempt.elapsed_seconds)
                if attempt.elapsed_seconds is not None
                else "—"
            ),
            "time_remaining_seconds": attempt.time_remaining_seconds,
            "timed_out": timed_out,
            "method": attempt.submission_method,
            "limit_seconds": mission_seconds(),
        },
    }


def _had_prior(attempt) -> bool:
    return GameAttempt.objects.filter(
        user_id=attempt.user_id,
        game_key=attempt.game_key,
        status__in=[GameAttempt.STATUS_COMPLETED, GameAttempt.STATUS_TIMED_OUT],
        id__lt=attempt.id,
    ).exists()
