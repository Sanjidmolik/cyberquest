"""Validate Gemini payloads; keep valid questions and report missing blueprint slots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

from question_bank.services.duplicate_detector import find_duplicates, similarity_ratio
from question_bank.services.source_validator import evidence_appears_grounded


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    insufficient: bool = False
    message: str = ""

    def fail(self, msg: str) -> "ValidationResult":
        self.ok = False
        self.errors.append(msg)
        return self


@dataclass
class SlotAcceptance:
    """Per-slot outcome while filtering a generation payload."""

    set_number: int
    question_number: int
    difficulty: str
    set_type: str
    question_type: str
    question: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.question is not None and not self.errors


@dataclass
class FilteredBankResult:
    """Validated questions placed into set slots; missing slots listed for repair."""

    sets: list[dict[str, Any]]
    accepted_questions: list[dict[str, Any]]
    missing_slots: list[dict[str, Any]]
    rejected_errors: list[str] = field(default_factory=list)
    insufficient: bool = False
    message: str = ""

    @property
    def requested(self) -> int:
        return sum(len(s.get("blueprint") or []) for s in self.sets) if False else 0

    @property
    def valid_count(self) -> int:
        return len(self.accepted_questions)

    @property
    def is_complete(self) -> bool:
        return not self.missing_slots and not self.insufficient


def validate_bank_configuration(
    *,
    total_sets: int,
    normal_sets: int,
    simulation_sets: int,
    questions_per_set: int,
) -> ValidationResult:
    result = ValidationResult(ok=True)
    if questions_per_set < 1:
        result.fail("questions_per_set must be >= 1.")
    if total_sets < 1:
        result.fail("total_sets must be >= 1.")
    if normal_sets + simulation_sets != total_sets:
        result.fail("normal_sets + simulation_sets must equal total_sets.")
    if normal_sets < 0 or simulation_sets < 0:
        result.fail("Set counts cannot be negative.")
    return result


def near_duplicate_threshold() -> float:
    try:
        return float(getattr(settings, "AI_NEAR_DUPLICATE_THRESHOLD", 0.88))
    except (TypeError, ValueError):
        return 0.88


def validate_single_question(
    question: Any,
    *,
    set_number: Any,
    set_type: str,
    source_content: str,
    expected_difficulty: str | None = None,
    expected_question_number: int | None = None,
    require_source: bool = True,
    label: str | None = None,
) -> list[str]:
    """Return validation errors for one question (empty list = valid)."""
    errors: list[str] = []
    qnum = expected_question_number or (
        question.get("question_number") if isinstance(question, dict) else "?"
    )
    tag = label or f"Set {set_number} Q{qnum}"

    if not isinstance(question, dict):
        return [f"{tag}: question must be an object."]

    prompt = (question.get("question") or "").strip()
    if not prompt:
        errors.append(f"{tag}: question text is empty.")

    options = question.get("options")
    if not isinstance(options, list) or len(options) < 2:
        errors.append(f"{tag}: options must be a list of at least 2 strings.")
        options = []
    elif any(not isinstance(o, str) or not o.strip() for o in options):
        errors.append(f"{tag}: every option must be a non-empty string.")

    correct = question.get("correct_answer")
    if not isinstance(correct, str) or not correct.strip():
        errors.append(f"{tag}: correct_answer is missing.")
    elif options and correct not in options:
        stripped_map = {o.strip(): o for o in options if isinstance(o, str)}
        if correct.strip() not in stripped_map:
            errors.append(f"{tag}: correct_answer is not one of the options.")

    explanation = (question.get("explanation") or "").strip()
    if not explanation:
        errors.append(f"{tag}: explanation is missing.")

    difficulty = (question.get("difficulty") or "").strip().lower()
    if difficulty not in {"beginner", "intermediate", "advanced"}:
        errors.append(f"{tag}: difficulty must be beginner|intermediate|advanced.")
    elif expected_difficulty and difficulty != expected_difficulty:
        errors.append(
            f"{tag}: difficulty '{difficulty}' does not match assigned "
            f"blueprint '{expected_difficulty}'."
        )

    if require_source:
        evidence = (question.get("source_evidence") or "").strip()
        if not evidence:
            errors.append(f"{tag}: source_evidence is missing.")
        elif not evidence_appears_grounded(source_content, evidence):
            errors.append(
                f"{tag}: source_evidence does not appear grounded in the source content."
            )
        material = (
            question.get("source_material")
            or question.get("source_section")
            or ""
        ).strip()
        if not material:
            # Soft preference encoded as warning-level but still required for source mode
            errors.append(f"{tag}: source_material is missing.")

    qtype = (question.get("question_type") or "").strip().lower()
    if set_type == "simulation":
        if qtype != "simulation":
            errors.append(f"{tag}: simulation set questions must have question_type 'simulation'.")
        scenario = question.get("scenario")
        if not isinstance(scenario, dict) or not scenario:
            errors.append(f"{tag}: simulation questions require a non-empty scenario object.")
    elif qtype == "simulation":
        scenario = question.get("scenario")
        if not isinstance(scenario, dict) or not scenario:
            errors.append(f"{tag}: simulation question_type requires scenario data.")

    return errors


def is_duplicate_against(
    prompt: str,
    existing_prompts: list[str],
    *,
    threshold: float | None = None,
) -> bool:
    thr = threshold if threshold is not None else near_duplicate_threshold()
    for other in existing_prompts:
        if similarity_ratio(prompt, other) >= thr:
            return True
    return False


def filter_payload_against_plans(
    payload: dict[str, Any],
    *,
    set_plans: list[dict[str, Any]],
    source_content: str,
    extra_existing_prompts: list[str] | None = None,
    require_source: bool = True,
) -> FilteredBankResult:
    """
    Accept valid questions into blueprint slots; collect missing slots for repair.

    Does NOT all-or-nothing reject the whole bank when some questions fail.
    """
    if not isinstance(payload, dict):
        return FilteredBankResult(
            sets=[],
            accepted_questions=[],
            missing_slots=_all_missing_slots(set_plans),
            rejected_errors=["Payload must be a JSON object."],
        )

    if payload.get("insufficient_source_content"):
        msg = (
            payload.get("message")
            or "Model reported insufficient source content for the requested bank."
        )
        return FilteredBankResult(
            sets=[],
            accepted_questions=[],
            missing_slots=_all_missing_slots(set_plans),
            rejected_errors=[msg],
            insufficient=True,
            message=msg,
        )

    plan_by_number = {int(p["set_number"]): p for p in set_plans}
    raw_sets = payload.get("sets") if isinstance(payload.get("sets"), list) else []
    questions_by_set: dict[int, dict[int, dict]] = {n: {} for n in plan_by_number}
    rejected: list[str] = []
    accepted_prompts: list[str] = list(extra_existing_prompts or [])

    for raw_set in raw_sets:
        if not isinstance(raw_set, dict):
            rejected.append("A set entry is not an object.")
            continue
        try:
            set_number = int(raw_set.get("set_number"))
        except (TypeError, ValueError):
            rejected.append("Set is missing a valid set_number.")
            continue
        plan = plan_by_number.get(set_number)
        if not plan:
            rejected.append(f"Unexpected set_number {set_number}.")
            continue

        set_type = (raw_set.get("set_type") or plan["set_type"]).strip().lower()
        if set_type != plan["set_type"]:
            rejected.append(
                f"Set {set_number}: set_type '{set_type}' does not match plan "
                f"'{plan['set_type']}'."
            )
            set_type = plan["set_type"]

        blueprint = plan["blueprint"]
        questions = raw_set.get("questions") if isinstance(raw_set.get("questions"), list) else []

        for question in questions:
            if not isinstance(question, dict):
                rejected.append(f"Set {set_number}: a question entry is not an object.")
                continue
            try:
                qnum = int(question.get("question_number"))
            except (TypeError, ValueError):
                rejected.append(f"Set {set_number}: question_number missing/invalid.")
                continue
            if qnum < 1 or qnum > len(blueprint):
                rejected.append(f"Set {set_number} Q{qnum}: out of blueprint range.")
                continue
            if qnum in questions_by_set[set_number]:
                rejected.append(f"Set {set_number} Q{qnum}: duplicate slot in response.")
                continue

            expected_diff = blueprint[qnum - 1]
            errors = validate_single_question(
                question,
                set_number=set_number,
                set_type=set_type,
                source_content=source_content,
                expected_difficulty=expected_diff,
                expected_question_number=qnum,
                require_source=require_source,
            )
            prompt = (question.get("question") or "").strip()
            if prompt and is_duplicate_against(prompt, accepted_prompts):
                errors.append(f"Set {set_number} Q{qnum}: duplicate of an existing question.")

            if errors:
                rejected.extend(errors)
                continue

            normalized = _normalize_question_dict(
                question,
                set_number=set_number,
                set_type=set_type,
                question_number=qnum,
                difficulty=expected_diff,
            )
            questions_by_set[set_number][qnum] = normalized
            accepted_prompts.append(prompt)

    built_sets: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for plan in set_plans:
        set_number = int(plan["set_number"])
        set_type = plan["set_type"]
        blueprint = plan["blueprint"]
        slot_map = questions_by_set.get(set_number, {})
        q_list = []
        for idx, diff in enumerate(blueprint, start=1):
            if idx in slot_map:
                q_list.append(slot_map[idx])
                accepted.append(slot_map[idx])
            else:
                missing.append({
                    "set_number": set_number,
                    "set_type": set_type,
                    "question_number": idx,
                    "difficulty": diff,
                    "question_type": plan.get("question_type") or (
                        "simulation" if set_type == "simulation" else "mcq"
                    ),
                })
        # Title from raw if present
        title = ""
        description = ""
        for raw_set in raw_sets:
            if isinstance(raw_set, dict) and raw_set.get("set_number") == set_number:
                title = (raw_set.get("title") or "")[:255]
                description = raw_set.get("description") or ""
                break
        if not title:
            title = f"{set_type.title()} Set {set_number}"
        built_sets.append({
            "set_number": set_number,
            "set_type": set_type,
            "title": title,
            "description": description,
            "questions": q_list,
            "blueprint": blueprint,
        })

    return FilteredBankResult(
        sets=built_sets,
        accepted_questions=accepted,
        missing_slots=missing,
        rejected_errors=rejected,
    )


def merge_replacements(
    filtered: FilteredBankResult,
    replacements: list[dict[str, Any]],
    *,
    set_plans: list[dict[str, Any]],
    source_content: str,
    require_source: bool = True,
) -> FilteredBankResult:
    """Validate repair replacements and fill matching missing slots."""
    plan_by_number = {int(p["set_number"]): p for p in set_plans}
    missing_index = {
        (int(s["set_number"]), int(s["question_number"])): s
        for s in filtered.missing_slots
    }
    accepted_prompts = [
        (q.get("question") or "").strip()
        for q in filtered.accepted_questions
        if (q.get("question") or "").strip()
    ]
    rejected = list(filtered.rejected_errors)
    sets_by_number = {int(s["set_number"]): s for s in filtered.sets}
    newly_accepted: list[dict[str, Any]] = []

    for raw in replacements or []:
        if not isinstance(raw, dict):
            rejected.append("Replacement entry is not an object.")
            continue
        try:
            set_number = int(raw.get("set_number"))
            qnum = int(raw.get("question_number"))
        except (TypeError, ValueError):
            rejected.append("Replacement missing set_number/question_number.")
            continue
        slot = missing_index.get((set_number, qnum))
        if not slot:
            rejected.append(f"Replacement Set {set_number} Q{qnum} is not a missing slot.")
            continue
        plan = plan_by_number[set_number]
        errors = validate_single_question(
            raw,
            set_number=set_number,
            set_type=slot["set_type"],
            source_content=source_content,
            expected_difficulty=slot["difficulty"],
            expected_question_number=qnum,
            require_source=require_source,
        )
        prompt = (raw.get("question") or "").strip()
        if prompt and is_duplicate_against(prompt, accepted_prompts):
            errors.append(f"Set {set_number} Q{qnum}: duplicate of an existing question.")
        if errors:
            rejected.extend(errors)
            continue

        normalized = _normalize_question_dict(
            raw,
            set_number=set_number,
            set_type=slot["set_type"],
            question_number=qnum,
            difficulty=slot["difficulty"],
        )
        # Insert keeping order
        q_list = sets_by_number[set_number]["questions"]
        q_list.append(normalized)
        q_list.sort(key=lambda q: int(q["question_number"]))
        newly_accepted.append(normalized)
        accepted_prompts.append(prompt)
        del missing_index[(set_number, qnum)]

    accepted = list(filtered.accepted_questions) + newly_accepted
    missing = list(missing_index.values())
    missing.sort(key=lambda s: (s["set_number"], s["question_number"]))

    return FilteredBankResult(
        sets=list(sets_by_number.values()),
        accepted_questions=accepted,
        missing_slots=missing,
        rejected_errors=rejected,
    )


def validate_generation_payload(
    payload: dict[str, Any],
    *,
    source_content: str,
    total_sets: int,
    normal_sets: int,
    simulation_sets: int,
    questions_per_set: int,
    set_plans: list[dict[str, Any]] | None = None,
) -> ValidationResult:
    """
    Strict full-bank validation (used by tests / callers that require completeness).

    Prefer ``filter_payload_against_plans`` for the repair-aware pipeline.
    """
    from question_bank.services.difficulty_blueprint import build_set_plans

    plans = set_plans or build_set_plans(
        total_sets=total_sets,
        normal_sets=normal_sets,
        simulation_sets=simulation_sets,
        questions_per_set=questions_per_set,
        difficulty_mode="mixed",
    )
    filtered = filter_payload_against_plans(
        payload,
        set_plans=plans,
        source_content=source_content,
    )
    result = ValidationResult(ok=True)
    if filtered.insufficient:
        result.ok = False
        result.insufficient = True
        result.message = filtered.message
        result.errors.append(filtered.message)
        return result

    if filtered.missing_slots:
        result.fail(
            f"Incomplete generation: {len(filtered.accepted_questions)} valid, "
            f"{len(filtered.missing_slots)} missing."
        )
    if filtered.rejected_errors:
        # Surface a sample of rejection reasons
        result.errors.extend(filtered.rejected_errors[:8])
        result.ok = False

    # Structural counts
    if len(filtered.sets) != total_sets:
        result.fail(f"Expected {total_sets} sets, got {len(filtered.sets)}.")
    normal_count = sum(1 for s in filtered.sets if s["set_type"] == "normal")
    simulation_count = sum(1 for s in filtered.sets if s["set_type"] == "simulation")
    if normal_count != normal_sets:
        result.fail(f"Expected {normal_sets} normal sets, got {normal_count}.")
    if simulation_count != simulation_sets:
        result.fail(f"Expected {simulation_sets} simulation sets, got {simulation_count}.")

    for s in filtered.sets:
        if len(s["questions"]) != questions_per_set:
            result.fail(
                f"Set {s['set_number']}: expected {questions_per_set} questions, "
                f"got {len(s['questions'])}."
            )

    result.ok = len(result.errors) == 0
    if not result.ok and not result.message:
        result.message = result.errors[0]
    return result


def _normalize_question_dict(
    question: dict[str, Any],
    *,
    set_number: int,
    set_type: str,
    question_number: int,
    difficulty: str,
) -> dict[str, Any]:
    material = (
        question.get("source_material")
        or question.get("source_section")
        or ""
    ).strip()
    return {
        "set_number": set_number,
        "set_type": set_type,
        "question_number": question_number,
        "question_type": (question.get("question_type") or (
            "simulation" if set_type == "simulation" else "mcq"
        )).strip().lower(),
        "question": str(question.get("question") or "").strip(),
        "options": [str(o).strip() for o in (question.get("options") or [])],
        "correct_answer": str(question.get("correct_answer") or "").strip(),
        "explanation": str(question.get("explanation") or "").strip(),
        "difficulty": difficulty,
        "source_material": material,
        "source_evidence": str(question.get("source_evidence") or "").strip(),
        "source_excerpt": str(question.get("source_excerpt") or "").strip(),
        "source_section": str(question.get("source_section") or material).strip()[:255],
        "scenario": question.get("scenario") if isinstance(question.get("scenario"), dict) else {},
    }


def _all_missing_slots(set_plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing = []
    for plan in set_plans:
        for idx, diff in enumerate(plan["blueprint"], start=1):
            missing.append({
                "set_number": plan["set_number"],
                "set_type": plan["set_type"],
                "question_number": idx,
                "difficulty": diff,
                "question_type": plan.get("question_type") or (
                    "simulation" if plan["set_type"] == "simulation" else "mcq"
                ),
            })
    return missing


# Back-compat alias used by older tests
def _validate_question(question, *, set_number, set_type, source_content, index):
    return validate_single_question(
        question,
        set_number=set_number,
        set_type=set_type,
        source_content=source_content,
        expected_question_number=index + 1,
        require_source=True,
        label=f"Set {set_number} Q{index + 1}",
    )
