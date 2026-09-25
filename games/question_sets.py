"""
Question-set services: ensure slots, generate AUTO sets, pick sets for users.

Approved AI Question Bank sets take priority over legacy ADMIN/AUTO slots.
"""

from __future__ import annotations

import random

from django.db import transaction
from django.db.models import Count

from .models import (
    AUTO_SET_NUMBERS,
    ADMIN_SET_NUMBERS,
    QUESTIONS_PER_SET,
    SET_COURSE_KEYS,
    GameAttempt,
    Question,
    QuestionSet,
    QuestionSetItem,
)


def ensure_set_slots(course: str | None = None) -> list[QuestionSet]:
    """Create the fixed 10 legacy slots (3 ADMIN + 7 AUTO) per course if missing."""
    courses = [course] if course else SET_COURSE_KEYS
    created = []
    for key in courses:
        for num in ADMIN_SET_NUMBERS:
            obj, was = QuestionSet.objects.get_or_create(
                course=key,
                set_number=num,
                question_bank=None,
                defaults={
                    "set_type": QuestionSet.SET_TYPE_ADMIN,
                    "is_active": True,
                    "status": QuestionSet.STATUS_APPROVED,
                },
            )
            if was:
                created.append(obj)
        for num in AUTO_SET_NUMBERS:
            obj, was = QuestionSet.objects.get_or_create(
                course=key,
                set_number=num,
                question_bank=None,
                defaults={
                    "set_type": QuestionSet.SET_TYPE_AUTO,
                    "is_active": True,
                    "status": QuestionSet.STATUS_APPROVED,
                },
            )
            if was:
                created.append(obj)
    return created


def set_status_rows(course: str) -> list[dict]:
    ensure_set_slots(course)
    rows = []
    for qs in QuestionSet.objects.filter(course=course, question_bank__isnull=True).annotate(
        qcount=Count("items")
    ):
        readiness = "READY" if qs.qcount == QUESTIONS_PER_SET else (
            "INVALID" if qs.qcount > QUESTIONS_PER_SET else "INCOMPLETE"
        )
        rows.append({
            "set": qs,
            "set_number": qs.set_number,
            "set_type": qs.set_type,
            "count": qs.qcount,
            "needed": QUESTIONS_PER_SET,
            "readiness": readiness,
            "is_active": qs.is_active,
        })
    return rows


def approved_bank_sets(course: str):
    """Approved sets belonging to an approved Question Bank for this domain."""
    from question_bank.models import QuestionBank

    qs = (
        QuestionSet.objects.filter(
            course=course,
            is_active=True,
            status=QuestionSet.STATUS_APPROVED,
            question_bank__isnull=False,
            question_bank__status=QuestionBank.STATUS_APPROVED,
        )
        .select_related("question_bank")
        .annotate(qcount=Count("items"))
    )
    # Filter in Python so expected count can vary per bank
    return [s for s in qs if s.qcount == s.question_bank.questions_per_set]


def legacy_usable_sets(course: str):
    ensure_set_slots(course)
    return (
        QuestionSet.objects.filter(
            course=course,
            is_active=True,
            question_bank__isnull=True,
            status=QuestionSet.STATUS_APPROVED,
        )
        .annotate(qcount=Count("items"))
        .filter(qcount=QUESTIONS_PER_SET)
    )


def usable_sets(course: str):
    """
    Prefer approved AI bank sets. Fall back to legacy ADMIN/AUTO READY sets
    so existing seeded courses keep working until banks are approved.
    """
    bank_sets = approved_bank_sets(course)
    if bank_sets:
        return bank_sets
    return list(legacy_usable_sets(course))


def pick_set_for_user(user, course: str) -> QuestionSet | None:
    """
    Prefer READY sets the user has not attempted yet.
    Bank-backed sets are tracked by question_set_id; legacy slots by set_number.
    After all attempted, pick randomly among READY sets.
    """
    ready = list(usable_sets(course))
    if not ready:
        return None

    attempted = list(
        GameAttempt.objects.filter(user=user, game_key=course, set_number__isnull=False)
        .values_list("question_set_id", "set_number")
    )
    attempted_set_ids = {sid for sid, _ in attempted if sid is not None}
    attempted_numbers = {num for _, num in attempted}

    unused = []
    for s in ready:
        if s.pk in attempted_set_ids:
            continue
        if s.question_bank_id is None and s.set_number in attempted_numbers:
            continue
        unused.append(s)

    pool = unused if unused else ready
    return random.choice(pool)


@transaction.atomic
def assign_questions_to_set(question_set: QuestionSet, questions: list[Question]) -> None:
    """Replace membership for a set. Does not delete the QuestionSet or attempts."""
    if len(questions) != len({q.pk for q in questions}):
        raise ValueError("Duplicate questions are not allowed inside one set.")
    QuestionSetItem.objects.filter(question_set=question_set).delete()
    QuestionSetItem.objects.bulk_create([
        QuestionSetItem(question_set=question_set, question=q, order=i)
        for i, q in enumerate(questions, start=1)
    ])
    question_set.save(update_fields=["updated_at"])


@transaction.atomic
def regenerate_auto_sets(course: str) -> dict:
    """
    Rebuild AUTO sets 4–10 from the active question pool.
    Does NOT touch ADMIN sets, bank-backed sets, GameAttempts, certificates, or competency.
    Increments version on each AUTO set.
    """
    ensure_set_slots(course)
    pool = list(
        Question.objects.filter(course=course, is_active=True, generated_by_ai=False)
        .order_by("id")
    )
    # Include AI questions in pool only if there are not enough seed questions
    if len(pool) < QUESTIONS_PER_SET:
        pool = list(Question.objects.filter(course=course, is_active=True).order_by("id"))

    if len(pool) < QUESTIONS_PER_SET:
        return {
            "ok": False,
            "generated": 0,
            "warning": (
                f"Not enough questions available to generate 7 unique sets. "
                f"Need at least {QUESTIONS_PER_SET} active questions for {course}; found {len(pool)}."
            ),
        }

    combos = _build_unique_combos(pool, count=7)
    if len(combos) < 7:
        return {
            "ok": False,
            "generated": len(combos),
            "warning": (
                "Not enough questions available to generate 7 unique sets. "
                f"Only {len(combos)} unique combinations of {QUESTIONS_PER_SET} could be formed "
                f"from {len(pool)} active questions. Add more questions and regenerate."
            ),
        }

    auto_sets = list(
        QuestionSet.objects.filter(
            course=course,
            set_type=QuestionSet.SET_TYPE_AUTO,
            question_bank__isnull=True,
        ).order_by("set_number")
    )
    for qs, combo in zip(auto_sets, combos):
        assign_questions_to_set(qs, combo)
        qs.version += 1
        qs.is_active = True
        qs.status = QuestionSet.STATUS_APPROVED
        qs.save(update_fields=["version", "is_active", "status", "updated_at"])

    return {"ok": True, "generated": 7, "warning": ""}


def _build_unique_combos(pool: list[Question], count: int) -> list[list[Question]]:
    """Prefer disjoint packing, then fill remaining unique combinations."""
    remaining = list(pool)
    random.shuffle(remaining)
    combos: list[list[Question]] = []
    used_keys: set[frozenset[int]] = set()

    while len(remaining) >= QUESTIONS_PER_SET and len(combos) < count:
        chunk = remaining[:QUESTIONS_PER_SET]
        remaining = remaining[QUESTIONS_PER_SET:]
        key = frozenset(q.pk for q in chunk)
        if key not in used_keys:
            used_keys.add(key)
            combos.append(chunk)

    attempts = 0
    max_attempts = 500
    while len(combos) < count and attempts < max_attempts:
        attempts += 1
        sample = random.sample(pool, QUESTIONS_PER_SET)
        key = frozenset(q.pk for q in sample)
        if key in used_keys:
            continue
        used_keys.add(key)
        combos.append(sample)

    return combos


def course_admin_summary() -> dict[str, list[dict]]:
    """Admin overview for all courses."""
    ensure_set_slots()
    summary = {}
    for key, label in [
        ("phishing_simulator", "Phishing"),
        ("password_cracker", "Password Security"),
        ("network_defense", "Network Defense"),
        ("cryptography", "Cryptography"),
        ("osint", "OSINT"),
    ]:
        summary[label] = set_status_rows(key)
    return summary
