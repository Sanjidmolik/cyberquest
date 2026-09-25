"""
Two-dimensional question selection: difficulty × question_type.

Selects from approved Question Bank pools. Never silently substitutes
a different difficulty or type when a required slot cannot be filled.
"""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from django.db.models import Count, Q

from games.game_config import get_game_question_config
from games.models import Question, QuestionSet
from question_bank.models import QuestionBank
from question_bank.services.difficulty_blueprint import (
    create_selection_plan,
    format_selection_plan_for_log,
)

logger = logging.getLogger(__name__)


class SelectionShortageError(Exception):
    """Raised when the approved pool cannot satisfy the selection plan."""

    def __init__(self, message: str, *, inventory: dict | None = None, shortages: list | None = None):
        super().__init__(message)
        self.inventory = inventory or {}
        self.shortages = shortages or []


@dataclass
class SelectionResult:
    questions: list[Question]
    plan: list[dict]
    question_ids: list[int] = field(default_factory=list)
    randomized: bool = True

    def to_quiz_dicts(self) -> list[dict]:
        return [q.to_quiz_dict() for q in self.questions]


def inventory_approved_questions(course: str) -> dict[str, dict[str, int]]:
    """
    Return counts keyed by difficulty → question_type for approved bank questions.

    Example: {"beginner": {"mcq": 4, "simulation": 2}, ...}
    """
    qs = (
        Question.objects.filter(
            course=course,
            is_active=True,
            difficulty__in=["beginner", "intermediate", "advanced"],
            sets__is_active=True,
            sets__status=QuestionSet.STATUS_APPROVED,
            sets__question_bank__isnull=False,
            sets__question_bank__status=QuestionBank.STATUS_APPROVED,
        )
        .values("difficulty", "question_type")
        .annotate(n=Count("id", distinct=True))
    )
    inv: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in qs:
        diff = (row["difficulty"] or "").strip().lower()
        qtype = (row["question_type"] or "mcq").strip().lower()
        if qtype == "true_false":
            qtype = "mcq"
        inv[diff][qtype] += row["n"]
    return {d: dict(types) for d, types in inv.items()}


def format_shortage_message(
    *,
    required_difficulty: str,
    required_type: str,
    available: int,
    required: int = 1,
    inventory: dict | None = None,
) -> str:
    type_label = "Simulation" if required_type == "simulation" else "MCQ"
    diff_label = required_difficulty.title()
    lines = [
        f"{diff_label} {type_label} questions available: {available}",
        f"Required: {required}",
        "",
        f"Please generate and approve more {diff_label} {type_label} questions.",
    ]
    if inventory:
        lines.append("")
        lines.append("Available inventory (difficulty × type):")
        for diff in ("beginner", "intermediate", "advanced"):
            types = inventory.get(diff) or {}
            lines.append(
                f"  {diff.title()}: MCQ={types.get('mcq', 0)}, "
                f"Simulation={types.get('simulation', 0)}"
            )
    return "\n".join(lines)


def resolve_attempt_config(course: str, bank: QuestionBank | None = None) -> dict[str, Any]:
    """Merge game defaults with optional QuestionBank attempt overrides."""
    cfg = get_game_question_config(course)
    allowed = tuple(cfg.get("allowed_types") or ("mcq",))
    size = int(cfg.get("attempt_size") or 5)
    mcq = cfg.get("default_mcq")
    sim = cfg.get("default_simulation")
    mode = cfg.get("difficulty_mode") or "mixed"

    if bank is not None:
        if bank.attempt_question_count:
            size = bank.attempt_question_count
        if bank.attempt_mcq_count is not None and bank.attempt_simulation_count is not None:
            mcq = bank.attempt_mcq_count
            sim = bank.attempt_simulation_count
        if bank.difficulty:
            mode = bank.difficulty

        # Constrain counts to allowed types
        if allowed == ("mcq",):
            mcq, sim = size, 0
        elif allowed == ("simulation",):
            mcq, sim = 0, size

    return {
        "attempt_size": size,
        "mcq_count": mcq,
        "simulation_count": sim,
        "allowed_types": allowed,
        "difficulty_mode": mode,
    }


def build_attempt_plan(course: str, bank: QuestionBank | None = None) -> list[dict]:
    cfg = resolve_attempt_config(course, bank)
    return create_selection_plan(
        question_count=cfg["attempt_size"],
        difficulty_mode=cfg["difficulty_mode"],
        mcq_count=cfg["mcq_count"],
        simulation_count=cfg["simulation_count"],
        allowed_types=cfg["allowed_types"],
    )


def approved_question_pool(course: str):
    """Queryable approved AI questions for a course/domain."""
    return (
        Question.objects.filter(
            course=course,
            is_active=True,
            difficulty__in=["beginner", "intermediate", "advanced"],
            sets__is_active=True,
            sets__status=QuestionSet.STATUS_APPROVED,
            sets__question_bank__isnull=False,
            sets__question_bank__status=QuestionBank.STATUS_APPROVED,
        )
        .distinct()
        .prefetch_related("sets")
    )


def plan_is_satisfiable(
    course: str,
    *,
    plan: list[dict] | None = None,
    bank: QuestionBank | None = None,
) -> bool:
    """Return True when approved inventory covers every (difficulty, type) slot."""
    plan = plan or build_attempt_plan(course, bank)
    inventory = inventory_approved_questions(course)
    needed: dict[tuple[str, str], int] = defaultdict(int)
    for slot in plan:
        qtype = slot["question_type"]
        if qtype == "true_false":
            qtype = "mcq"
        needed[(slot["difficulty"], qtype)] += 1
    for (diff, qtype), req in needed.items():
        available = (inventory.get(diff) or {}).get(qtype, 0)
        if available < req:
            return False
    return True


def pool_supports_balanced_selection(course: str, bank: QuestionBank | None = None) -> bool:
    """
    True when the approved pool can fully satisfy the attempt plan.

    If inventory is incomplete, gameplay falls back to whole-set selection
    instead of blocking with a shortage (shortage is still raised when
    selection is forced / called directly).
    """
    if bank is None:
        bank = latest_approved_bank(course)
    if not approved_question_pool(course).exists():
        return False
    return plan_is_satisfiable(course, bank=bank)


def select_questions_for_attempt(
    course: str,
    *,
    plan: list[dict] | None = None,
    bank: QuestionBank | None = None,
    rng: random.Random | None = None,
) -> SelectionResult:
    """
    Select questions matching each (difficulty, question_type) slot.

    Raises SelectionShortageError without substituting other buckets.
    """
    rng = rng or random.Random()
    plan = plan or build_attempt_plan(course, bank)
    logger.info(
        "Selection plan for %s:\n%s",
        course,
        format_selection_plan_for_log(plan),
    )

    inventory = inventory_approved_questions(course)
    pool = list(approved_question_pool(course))

    # Bucket pool
    buckets: dict[tuple[str, str], list[Question]] = defaultdict(list)
    for q in pool:
        qtype = q.question_type
        if qtype == Question.TYPE_TRUE_FALSE:
            qtype = Question.TYPE_MCQ
        buckets[(q.difficulty, qtype)].append(q)

    for key in buckets:
        rng.shuffle(buckets[key])

    # Count requirements first for clear shortage reporting
    needed: dict[tuple[str, str], int] = defaultdict(int)
    for slot in plan:
        qtype = slot["question_type"]
        if qtype == "true_false":
            qtype = "mcq"
        needed[(slot["difficulty"], qtype)] += 1

    shortages = []
    for (diff, qtype), req in needed.items():
        available = len(buckets.get((diff, qtype), []))
        if available < req:
            shortages.append({
                "difficulty": diff,
                "question_type": qtype,
                "required": req,
                "available": available,
            })

    if shortages:
        # Prefer reporting the first critical shortage clearly
        first = shortages[0]
        msg = format_shortage_message(
            required_difficulty=first["difficulty"],
            required_type=first["question_type"],
            available=first["available"],
            required=first["required"],
            inventory=inventory,
        )
        raise SelectionShortageError(msg, inventory=inventory, shortages=shortages)

    selected: list[Question] = []
    used_ids: set[int] = set()
    for slot in plan:
        qtype = slot["question_type"]
        if qtype == "true_false":
            qtype = "mcq"
        key = (slot["difficulty"], qtype)
        bucket = buckets[key]
        pick = None
        while bucket:
            candidate = bucket.pop()
            if candidate.pk not in used_ids:
                pick = candidate
                break
        if pick is None:
            # Should not happen after pre-check, but guard anyway
            raise SelectionShortageError(
                format_shortage_message(
                    required_difficulty=slot["difficulty"],
                    required_type=qtype,
                    available=0,
                    required=1,
                    inventory=inventory,
                ),
                inventory=inventory,
                shortages=[{
                    "difficulty": slot["difficulty"],
                    "question_type": qtype,
                    "required": 1,
                    "available": 0,
                }],
            )
        used_ids.add(pick.pk)
        selected.append(pick)

    # Randomize display order while keeping IDs for session stability rebuild
    order = list(range(len(selected)))
    rng.shuffle(order)
    ordered = [selected[i] for i in order]

    return SelectionResult(
        questions=ordered,
        plan=plan,
        question_ids=[q.pk for q in ordered],
        randomized=True,
    )


def load_questions_by_ids(question_ids: list[int]) -> list[Question]:
    """Reload questions in the exact stored order (stable after refresh)."""
    if not question_ids:
        return []
    by_id = {
        q.pk: q
        for q in Question.objects.filter(pk__in=question_ids, is_active=True)
    }
    return [by_id[qid] for qid in question_ids if qid in by_id]


def latest_approved_bank(course: str) -> QuestionBank | None:
    return (
        QuestionBank.objects.filter(
            domain=course,
            status=QuestionBank.STATUS_APPROVED,
        )
        .order_by("-generated_at", "-id")
        .first()
    )
