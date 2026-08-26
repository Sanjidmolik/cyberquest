"""
games/views.py
------------------
quiz_game() is a GENERIC view that serves ANY game defined in
quiz_data.QUIZ_GAMES (currently: cryptography, osint, steganography,
network_defense). Adding a 5th quiz-style game later means adding an
entry to quiz_data.py -- no new view function needed.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import Http404

from .models import GameAttempt
from .quiz_data import QUIZ_GAMES
from courses.progress import has_completed_all_courses
from achievements.checks import check_and_award_badges

XP_PER_CORRECT_ANSWER = 20


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


@login_required(login_url="/accounts/login/")
def quiz_game(request, game_key):
    """Generic multiple-choice quiz game, driven entirely by QUIZ_GAMES data."""

    game = QUIZ_GAMES.get(game_key)
    if game is None:
        raise Http404("No such game.")

    blocked = _require_course_completed(request)
    if blocked:
        return blocked

    questions = game["questions"]

    if request.method == "POST":
        score = 0
        results = []

        for question in questions:
            submitted = request.POST.get(f"question_{question['id']}")
            try:
                submitted_index = int(submitted)
            except (TypeError, ValueError):
                submitted_index = -1

            correct = (submitted_index == question["correct_index"])
            if correct:
                score += 1

            results.append({
                "prompt": question["prompt"],
                "correct": correct,
                "correct_answer": question["options"][question["correct_index"]],
                "explanation": question["explanation"],
            })

        total = len(questions)
        already_completed = GameAttempt.objects.filter(user=request.user, game_key=game_key).exists()

        xp_awarded = 0
        leveled_up = False
        if not already_completed:
            xp_awarded = score * XP_PER_CORRECT_ANSWER
            leveled_up = _apply_xp_and_level_up(request.user, xp_awarded)

        GameAttempt.objects.create(user=request.user, game_key=game_key,
                                    score=score, total_questions=total, xp_awarded=xp_awarded)

        if xp_awarded:
            messages.success(request, f"+{xp_awarded} XP earned!")
        if leveled_up:
            messages.success(request, f"Level up! You're now Level {request.user.level}.")

        for badge in check_and_award_badges(request.user):
            messages.success(request, f"🏆 New badge unlocked: {badge.icon_emoji} {badge.name}!")

        return render(request, "games/quiz_result.html", {
            "game": game, "score": score, "total": total,
            "results": results, "xp_awarded": xp_awarded, "already_completed": already_completed,
        })

    return render(request, "games/quiz_game.html", {"game": game, "game_key": game_key, "questions": questions})
