"""
Question bank generation orchestration.

CyberQuest owns difficulty blueprints and the repair loop.
Gemini analyzes source content and fills assigned slots.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from games.models import Question, QuestionSet, QuestionSetItem
from question_bank.models import QuestionBank
from question_bank.services.difficulty_blueprint import (
    build_set_plans,
    format_blueprint_for_log,
)
from question_bank.services.providers.gemini import (
    GeminiProviderError,
    get_ai_provider,
)
from question_bank.services.source_validator import estimate_source_capacity
from question_bank.services.validator import (
    filter_payload_against_plans,
    merge_replacements,
    validate_bank_configuration,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_REPAIR_ATTEMPTS = 3


class QuestionGenerationError(Exception):
    def __init__(self, message: str, *, insufficient: bool = False):
        super().__init__(message)
        self.insufficient = insufficient


def generate_question_bank(bank_id: int, *, created_by=None) -> QuestionBank:
    """
    Generate (or regenerate) sets/questions for a QuestionBank.

    Pipeline:
      blueprint → Gemini (content-aware) → validate slots → repair missing → save

    Status:
      REVIEW  — all slots filled (ready for admin review/approval)
      PARTIAL — some valid questions saved; not student-visible until completed/approved
      FAILED  — nothing usable
    """
    bank = QuestionBank.objects.get(pk=bank_id)
    logger.info("Question bank generation started bank_id=%s title=%r", bank.pk, bank.title)

    cfg = validate_bank_configuration(
        total_sets=bank.total_sets,
        normal_sets=bank.normal_sets,
        simulation_sets=bank.simulation_sets,
        questions_per_set=bank.questions_per_set,
    )
    if not cfg.ok:
        return _mark_failed(bank, "; ".join(cfg.errors))

    # Advisory only — never hard-fail on short sources.
    _, capacity_note = estimate_source_capacity(
        bank.source_content,
        bank.expected_total_questions,
    )
    if capacity_note:
        logger.info("Source capacity note bank_id=%s: %s", bank.pk, capacity_note)

    set_plans = build_set_plans(
        total_sets=bank.total_sets,
        normal_sets=bank.normal_sets,
        simulation_sets=bank.simulation_sets,
        questions_per_set=bank.questions_per_set,
        difficulty_mode=bank.difficulty,
    )

    for plan in set_plans:
        logger.info(
            "QuestionSet plan bank_id=%s set=%s type=%s blueprint:\n%s",
            bank.pk,
            plan["set_number"],
            plan["set_type"],
            format_blueprint_for_log(plan["blueprint"]),
        )

    bank.status = QuestionBank.STATUS_GENERATING
    bank.last_error = ""
    bank.ai_provider = getattr(settings, "AI_PROVIDER", "gemini") or "gemini"
    bank.ai_model = getattr(settings, "GEMINI_MODEL", "") or ""
    if created_by is not None and bank.created_by_id is None:
        bank.created_by = created_by
    bank.save(update_fields=[
        "status", "last_error", "ai_provider", "ai_model", "created_by", "updated_at",
    ])

    existing_domain_prompts = list(
        Question.objects.filter(
            course=bank.domain,
            is_active=True,
        )
        .exclude(sets__question_bank=bank)
        .values_list("prompt", flat=True)[:800]
    )

    try:
        provider = get_ai_provider()
        payload = provider.generate_question_bank(
            source_content=bank.source_content,
            domain=bank.domain,
            language=bank.resolve_output_language(),
            difficulty=bank.difficulty,
            total_sets=bank.total_sets,
            normal_sets=bank.normal_sets,
            simulation_sets=bank.simulation_sets,
            questions_per_set=bank.questions_per_set,
            set_plans=set_plans,
        )
        used_model = getattr(provider, "model", None)
        if isinstance(used_model, str) and used_model and used_model != bank.ai_model:
            bank.ai_model = used_model
            bank.save(update_fields=["ai_model", "updated_at"])
    except GeminiProviderError as exc:
        logger.warning("Gemini API failure bank_id=%s: %s", bank.pk, exc)
        return _mark_failed(bank, str(exc))
    except Exception:
        logger.exception("Unexpected generation failure bank_id=%s", bank.pk)
        return _mark_failed(
            bank,
            "Question generation failed: unexpected server error.",
        )

    filtered = filter_payload_against_plans(
        payload,
        set_plans=set_plans,
        source_content=bank.source_content,
        extra_existing_prompts=existing_domain_prompts,
        require_source=True,
    )

    requested = bank.expected_total_questions
    logger.info(
        "Initial AI filter bank_id=%s requested=%s valid=%s missing=%s",
        bank.pk,
        requested,
        len(filtered.accepted_questions),
        len(filtered.missing_slots),
    )

    max_repair = int(getattr(settings, "AI_MAX_REPAIR_ATTEMPTS", DEFAULT_MAX_REPAIR_ATTEMPTS))
    for attempt in range(1, max_repair + 1):
        if not filtered.missing_slots:
            break
        logger.info(
            "Repair attempt %s/%s bank_id=%s missing=%s",
            attempt,
            max_repair,
            bank.pk,
            len(filtered.missing_slots),
        )
        try:
            repair_payload = provider.generate_replacements(
                source_content=bank.source_content,
                domain=bank.domain,
                language=bank.resolve_output_language(),
                missing_slots=filtered.missing_slots,
                existing_questions=filtered.accepted_questions,
            )
        except GeminiProviderError as exc:
            logger.warning(
                "Repair attempt %s failed bank_id=%s: %s",
                attempt,
                bank.pk,
                exc,
            )
            continue
        except Exception:
            logger.exception("Unexpected repair failure bank_id=%s attempt=%s", bank.pk, attempt)
            continue

        if repair_payload.get("insufficient_source_content"):
            logger.info(
                "Repair reported insufficient content bank_id=%s: %s",
                bank.pk,
                repair_payload.get("message"),
            )
            break

        replacements = repair_payload.get("replacements") or []
        if not isinstance(replacements, list):
            replacements = []

        before_missing = len(filtered.missing_slots)
        filtered = merge_replacements(
            filtered,
            replacements,
            set_plans=set_plans,
            source_content=bank.source_content,
            require_source=True,
        )
        logger.info(
            "Repair attempt %s result bank_id=%s generated=%s valid_now=%s missing=%s (was %s)",
            attempt,
            bank.pk,
            len(replacements),
            len(filtered.accepted_questions),
            len(filtered.missing_slots),
            before_missing,
        )

    if not filtered.accepted_questions:
        msg = filtered.message or (
            "; ".join(filtered.rejected_errors[:5])
            if filtered.rejected_errors
            else "Question generation produced no valid questions."
        )
        return _mark_failed(bank, msg, insufficient=filtered.insufficient)

    complete = filtered.is_complete
    try:
        with transaction.atomic():
            _clear_bank_content(bank)
            _persist_filtered(bank, filtered)
            bank.generated_at = timezone.now()
            bank.generation_version = (bank.generation_version or 0) + 1
            if complete:
                bank.status = QuestionBank.STATUS_REVIEW
                bank.last_error = ""
            else:
                bank.status = QuestionBank.STATUS_PARTIAL
                bank.last_error = (
                    f"Partial generation: {len(filtered.accepted_questions)}/{requested} "
                    f"valid questions. Missing {len(filtered.missing_slots)} slot(s). "
                    "Not available to students until generation is completed and approved."
                )
            bank.save(update_fields=[
                "status", "last_error", "generated_at", "generation_version", "updated_at",
            ])
    except Exception:
        logger.exception("Database persistence failure bank_id=%s", bank.pk)
        return _mark_failed(
            bank,
            "Question generation failed while saving validated results.",
        )

    logger.info(
        "Question bank generation finished bank_id=%s status=%s valid=%s/%s",
        bank.pk,
        bank.status,
        len(filtered.accepted_questions),
        requested,
    )
    return bank


def _mark_failed(bank: QuestionBank, message: str, *, insufficient: bool = False) -> QuestionBank:
    bank.status = QuestionBank.STATUS_FAILED
    bank.last_error = message
    bank.save(update_fields=["status", "last_error", "updated_at"])
    _clear_bank_content(bank)
    if insufficient:
        logger.info("Insufficient source content bank_id=%s", bank.pk)
    return bank


def _clear_bank_content(bank: QuestionBank) -> None:
    """Delete sets (and their items) for this bank. Orphan AI questions are removed."""
    sets = list(QuestionSet.objects.filter(question_bank=bank).prefetch_related("items"))
    question_ids: set[int] = set()
    for qset in sets:
        question_ids.update(qset.items.values_list("question_id", flat=True))
    QuestionSet.objects.filter(question_bank=bank).delete()
    if question_ids:
        orphan_ids = []
        for qid in question_ids:
            if not QuestionSetItem.objects.filter(question_id=qid).exists():
                orphan_ids.append(qid)
        if orphan_ids:
            Question.objects.filter(id__in=orphan_ids, generated_by_ai=True).delete()


def _persist_filtered(bank: QuestionBank, filtered) -> None:
    for raw_set in filtered.sets:
        set_type = (
            QuestionSet.SET_TYPE_SIMULATION
            if raw_set["set_type"] == "simulation"
            else QuestionSet.SET_TYPE_NORMAL
        )
        complete_set = len(raw_set["questions"]) == len(raw_set.get("blueprint") or raw_set["questions"])
        # Incomplete sets stay DRAFT so they cannot be approved/played accidentally.
        set_status = (
            QuestionSet.STATUS_REVIEW if complete_set and filtered.is_complete
            else QuestionSet.STATUS_DRAFT
        )
        # When bank is fully complete, all sets are REVIEW.
        if filtered.is_complete:
            set_status = QuestionSet.STATUS_REVIEW

        qset = QuestionSet.objects.create(
            course=bank.domain,
            set_number=int(raw_set["set_number"]),
            set_type=set_type,
            is_active=True,
            version=1,
            question_bank=bank,
            status=set_status,
            title=(raw_set.get("title") or "")[:255],
            description=raw_set.get("description") or "",
        )
        items = []
        for raw_q in raw_set["questions"]:
            question = _create_question(bank, raw_q, set_type=set_type)
            items.append(
                QuestionSetItem(
                    question_set=qset,
                    question=question,
                    order=int(raw_q.get("question_number") or 0) or (len(items) + 1),
                )
            )
        QuestionSetItem.objects.bulk_create(items)


def _create_question(bank: QuestionBank, raw_q: dict[str, Any], *, set_type: str) -> Question:
    options = [str(o).strip() for o in raw_q["options"]]
    correct_answer = str(raw_q["correct_answer"]).strip()
    try:
        correct_index = options.index(correct_answer)
    except ValueError:
        stripped = [o.strip() for o in options]
        correct_index = stripped.index(correct_answer)

    qtype = (raw_q.get("question_type") or "mcq").strip().lower()
    if set_type == QuestionSet.SET_TYPE_SIMULATION:
        qtype = Question.TYPE_SIMULATION
    elif qtype not in {Question.TYPE_MCQ, Question.TYPE_TRUE_FALSE, Question.TYPE_SIMULATION}:
        qtype = Question.TYPE_MCQ

    scenario = raw_q.get("scenario") if isinstance(raw_q.get("scenario"), dict) else {}
    difficulty = (raw_q.get("difficulty") or "").strip().lower()
    if difficulty not in {
        Question.DIFF_BEGINNER,
        Question.DIFF_INTERMEDIATE,
        Question.DIFF_ADVANCED,
    }:
        difficulty = ""

    material = (
        raw_q.get("source_material")
        or raw_q.get("source_section")
        or ""
    ).strip()[:255]

    return Question.objects.create(
        course=bank.domain,
        prompt=str(raw_q["question"]).strip(),
        options=options,
        correct_index=correct_index,
        explanation=str(raw_q.get("explanation") or "").strip(),
        correct_feedback="Correct!",
        wrong_feedback="Incorrect.",
        is_active=True,
        question_type=qtype,
        question_number=raw_q.get("question_number"),
        difficulty=difficulty,
        source_evidence=str(raw_q.get("source_evidence") or "").strip(),
        source_excerpt=str(raw_q.get("source_excerpt") or "").strip(),
        source_section=material,
        scenario_data=scenario or {},
        generated_by_ai=True,
        manually_edited=False,
    )
