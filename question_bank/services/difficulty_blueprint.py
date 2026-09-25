"""
Deterministic difficulty blueprints controlled by CyberQuest (not Gemini).

Documented mixed distributions:
  5 questions → 2 beginner + 2 intermediate + 1 advanced
 10 questions → 3 beginner + 4 intermediate + 3 advanced
  n >= 6     → ~30% beginner, ~40% intermediate, ~30% advanced
"""

from __future__ import annotations

DIFFICULTIES = ("beginner", "intermediate", "advanced")
VALID_MODES = (*DIFFICULTIES, "mixed")


def create_difficulty_blueprint(
    question_count: int,
    difficulty_mode: str = "mixed",
) -> list[str]:
    """
    Return a list of per-question difficulties of length ``question_count``.

    Admin-controlled single difficulty modes yield a uniform blueprint.
    Mixed mode yields a balanced deterministic distribution.
    """
    count = int(question_count)
    if count < 1:
        return []

    mode = (difficulty_mode or "mixed").strip().lower()
    if mode not in VALID_MODES:
        mode = "mixed"

    if mode in DIFFICULTIES:
        return [mode] * count

    return _mixed_blueprint(count)


def _mixed_blueprint(count: int) -> list[str]:
    if count == 1:
        return ["intermediate"]
    if count == 2:
        return ["beginner", "intermediate"]
    if count == 3:
        return ["beginner", "intermediate", "advanced"]
    if count == 4:
        return ["beginner", "beginner", "intermediate", "advanced"]
    if count == 5:
        return ["beginner", "beginner", "intermediate", "intermediate", "advanced"]
    if count == 10:
        return (
            ["beginner"] * 3
            + ["intermediate"] * 4
            + ["advanced"] * 3
        )

    beginners = max(1, round(count * 0.30))
    advanced = max(1, round(count * 0.30))
    intermediate = count - beginners - advanced
    if intermediate < 1:
        intermediate = 1
        # Rebalance so totals match count
        overflow = beginners + intermediate + advanced - count
        while overflow > 0:
            if beginners >= advanced and beginners > 1:
                beginners -= 1
            elif advanced > 1:
                advanced -= 1
            else:
                intermediate = max(1, intermediate - 1)
            overflow = beginners + intermediate + advanced - count
    while beginners + intermediate + advanced < count:
        intermediate += 1
    while beginners + intermediate + advanced > count:
        if intermediate > 1:
            intermediate -= 1
        elif beginners > 1:
            beginners -= 1
        else:
            advanced = max(1, advanced - 1)

    return (
        ["beginner"] * beginners
        + ["intermediate"] * intermediate
        + ["advanced"] * advanced
    )


def create_type_blueprint(
    question_count: int,
    *,
    mcq_count: int | None = None,
    simulation_count: int | None = None,
    allowed_types: tuple[str, ...] | list[str] = ("mcq", "simulation"),
) -> list[str]:
    """
    Return a list of per-question types of length ``question_count``.

    Independent from difficulty. Admin / game config supplies counts.
    """
    count = int(question_count)
    if count < 1:
        return []

    allowed = tuple(t for t in allowed_types if t in ("mcq", "simulation", "true_false"))
    if not allowed:
        allowed = ("mcq",)

    if allowed == ("mcq",) or allowed == ("true_false",):
        return ["mcq"] * count
    if allowed == ("simulation",):
        return ["simulation"] * count

    # Both MCQ and simulation allowed
    if mcq_count is None and simulation_count is None:
        mcq_count = count // 2
        simulation_count = count - mcq_count
    elif mcq_count is None:
        simulation_count = int(simulation_count)
        mcq_count = count - simulation_count
    elif simulation_count is None:
        mcq_count = int(mcq_count)
        simulation_count = count - mcq_count
    else:
        mcq_count = int(mcq_count)
        simulation_count = int(simulation_count)

    if mcq_count < 0 or simulation_count < 0:
        raise ValueError("MCQ and simulation counts cannot be negative.")
    if mcq_count + simulation_count != count:
        raise ValueError(
            f"mcq_count ({mcq_count}) + simulation_count ({simulation_count}) "
            f"must equal question_count ({count})."
        )

    # Interleave for coverage rather than dumping all MCQs first.
    from collections import deque

    q_mcq = deque(["mcq"] * mcq_count)
    q_sim = deque(["simulation"] * simulation_count)
    types: list[str] = []
    # Lead with the larger bucket so leftovers trail evenly
    lead_sim = simulation_count > mcq_count
    while q_mcq or q_sim:
        if lead_sim:
            if q_sim:
                types.append(q_sim.popleft())
            if q_mcq:
                types.append(q_mcq.popleft())
        else:
            if q_mcq:
                types.append(q_mcq.popleft())
            if q_sim:
                types.append(q_sim.popleft())
    return types


def create_selection_plan(
    *,
    question_count: int = 5,
    difficulty_mode: str = "mixed",
    mcq_count: int | None = None,
    simulation_count: int | None = None,
    allowed_types: tuple[str, ...] | list[str] = ("mcq", "simulation"),
) -> list[dict]:
    """
    Two-dimensional plan: each slot has independent difficulty + question_type.

    Example (5 mixed, 2 MCQ + 3 simulation):
      [
        {"difficulty": "beginner", "question_type": "mcq"},
        {"difficulty": "beginner", "question_type": "simulation"},
        ...
      ]
    """
    difficulties = create_difficulty_blueprint(question_count, difficulty_mode)
    types = create_type_blueprint(
        question_count,
        mcq_count=mcq_count,
        simulation_count=simulation_count,
        allowed_types=allowed_types,
    )
    return [
        {"difficulty": d, "question_type": t, "slot": i}
        for i, (d, t) in enumerate(zip(difficulties, types), start=1)
    ]


def format_blueprint_for_log(blueprint: list[str]) -> str:
    lines = [f"  Q{i} {diff.title()}" for i, diff in enumerate(blueprint, start=1)]
    return "\n".join(lines)


def format_selection_plan_for_log(plan: list[dict]) -> str:
    lines = [
        f"  Q{s['slot']} {s['difficulty'].title()} + {s['question_type']}"
        for s in plan
    ]
    return "\n".join(lines)


def build_set_plans(
    *,
    total_sets: int,
    normal_sets: int,
    simulation_sets: int,
    questions_per_set: int,
    difficulty_mode: str,
) -> list[dict]:
    """
    Build generation plans for each set.

    Each plan: {set_number, set_type, blueprint, question_type_hint}
    """
    plans: list[dict] = []
    for set_number in range(1, total_sets + 1):
        if set_number <= normal_sets:
            set_type = "normal"
            qtype = "mcq"
        else:
            set_type = "simulation"
            qtype = "simulation"
        plans.append({
            "set_number": set_number,
            "set_type": set_type,
            "question_type": qtype,
            "blueprint": create_difficulty_blueprint(questions_per_set, difficulty_mode),
        })
    # simulation_sets is validated by config; unused beyond layout
    _ = simulation_sets
    return plans
