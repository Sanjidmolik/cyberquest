"""
games/views.py
-----------------
Handles the Phishing Simulator gameplay:
  - GET  -> show the quiz questions
  - POST -> grade the answers, award XP (first completion only), show results

Quiz CONTENT lives in data.py. XP/leveling math lives in this file only,
kept in one small helper function so it's easy to find and tune.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages

from .data import PHISHING_QUESTIONS, PASSWORD_QUESTIONS
from .models import GameAttempt
from courses.progress import has_completed_all_courses

XP_PER_CORRECT_ANSWER = 20


def _require_course_completed(request):
    """
    Shared gate for every game view: even though the dashboard already
    hides game links until the course intro is read, a user could still
    type a game's URL directly. This function re-checks the same rule
    server-side so that shortcut doesn't work either.

    Returns a redirect response if blocked, or None if the user may proceed.
    """
    if not has_completed_all_courses(request.user):
        messages.error(request, "Please complete the course introduction first.")
        return redirect("courses:intro")
    return None


def _apply_xp_and_level_up(user, xp_gained):
    """
    Add XP to the user and recalculate their level.
    Kept as one small function so the "100 XP per level" rule lives in
    exactly one place -- if you want to change the leveling curve later,
    this is the only spot to touch.
    """
    user.xp += xp_gained
    new_level = (user.xp // 100) + 1
    leveled_up = new_level > user.level
    user.level = new_level
    user.save(update_fields=["xp", "level"])
    return leveled_up


@login_required(login_url="/accounts/login/")
def phishing_simulator(request):
    """Show the phishing simulator quiz and grade submissions."""

    blocked = _require_course_completed(request)
    if blocked:
        return blocked

    if request.method == "POST":
        score = 0
        results = []  # per-question feedback shown after grading

        for question in PHISHING_QUESTIONS:
            field_name = f"question_{question['id']}"
            user_answer = request.POST.get(field_name)  # "phishing" or "legit"
            user_said_phishing = (user_answer == "phishing")
            correct = (user_said_phishing == question["is_phishing"])

            if correct:
                score += 1

            results.append({
                "subject": question["subject"],
                "correct": correct,
                "is_phishing": question["is_phishing"],
                "red_flags": question["red_flags"],
            })

        total = len(PHISHING_QUESTIONS)

        # Only award XP the FIRST time this user completes this game --
        # prevents infinite XP farming by resubmitting the same quiz.
        already_completed = GameAttempt.objects.filter(
            user=request.user, game_key="phishing_simulator"
        ).exists()

        xp_awarded = 0
        leveled_up = False
        if not already_completed:
            xp_awarded = score * XP_PER_CORRECT_ANSWER
            leveled_up = _apply_xp_and_level_up(request.user, xp_awarded)

        GameAttempt.objects.create(
            user=request.user,
            game_key="phishing_simulator",
            score=score,
            total_questions=total,
            xp_awarded=xp_awarded,
        )

        if xp_awarded:
            messages.success(request, f"+{xp_awarded} XP earned!")
        if leveled_up:
            messages.success(request, f"Level up! You're now Level {request.user.level}.")

        return render(request, "games/phishing_result.html", {
            "score": score,
            "total": total,
            "results": results,
            "xp_awarded": xp_awarded,
            "already_completed": already_completed,
        })

    # GET request -- show the quiz form
    return render(request, "games/phishing_simulator.html", {
        "questions": PHISHING_QUESTIONS,
    })


@login_required(login_url="/accounts/login/")
def password_cracker(request):
    """
    Password Cracker Challenge: user classifies each candidate password
    as Weak, Medium, or Strong. Mirrors phishing_simulator's structure
    exactly (grading, XP, anti-farming) so the two games stay consistent.
    """

    blocked = _require_course_completed(request)
    if blocked:
        return blocked

    if request.method == "POST":
        score = 0
        results = []

        for question in PASSWORD_QUESTIONS:
            field_name = f"question_{question['id']}"
            user_answer = request.POST.get(field_name)  # "weak" / "medium" / "strong"
            correct = (user_answer == question["strength"])

            if correct:
                score += 1

            results.append({
                "password": question["password"],
                "correct": correct,
                "strength": question["strength"],
                "explanation": question["explanation"],
            })

        total = len(PASSWORD_QUESTIONS)

        already_completed = GameAttempt.objects.filter(
            user=request.user, game_key="password_cracker"
        ).exists()

        xp_awarded = 0
        leveled_up = False
        if not already_completed:
            xp_awarded = score * XP_PER_CORRECT_ANSWER
            leveled_up = _apply_xp_and_level_up(request.user, xp_awarded)

        GameAttempt.objects.create(
            user=request.user,
            game_key="password_cracker",
            score=score,
            total_questions=total,
            xp_awarded=xp_awarded,
        )

        if xp_awarded:
            messages.success(request, f"+{xp_awarded} XP earned!")
        if leveled_up:
            messages.success(request, f"Level up! You're now Level {request.user.level}.")

        return render(request, "games/password_result.html", {
            "score": score,
            "total": total,
            "results": results,
            "xp_awarded": xp_awarded,
            "already_completed": already_completed,
        })

    return render(request, "games/password_cracker.html", {
        "questions": PASSWORD_QUESTIONS,
    })
