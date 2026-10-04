"""
API-ready JSON endpoints for Question Banks (staff-only).

No DRF dependency — plain Django JsonResponse views for a future Next.js client.
Students never receive draft/review content through these endpoints.
"""

from __future__ import annotations

import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from games.models import Question, QuestionSet
from question_bank.models import QuestionBank
from question_bank.services.generator import generate_question_bank


def _bank_dict(bank: QuestionBank) -> dict:
    return {
        "id": bank.pk,
        "title": bank.title,
        "description": bank.description,
        "domain": bank.domain,
        "status": bank.status,
        "total_sets": bank.total_sets,
        "normal_sets": bank.normal_sets,
        "simulation_sets": bank.simulation_sets,
        "questions_per_set": bank.questions_per_set,
        "difficulty": bank.difficulty,
        "output_language": bank.output_language,
        "ai_provider": bank.ai_provider,
        "ai_model": bank.ai_model,
        "generation_version": bank.generation_version,
        "last_error": bank.last_error,
        "generation_stage": bank.generation_stage,
        "generation_completed": bank.generation_completed,
        "generation_requested": bank.generation_requested,
        "created_at": bank.created_at.isoformat() if bank.created_at else None,
        "generated_at": bank.generated_at.isoformat() if bank.generated_at else None,
    }


def _set_dict(qset: QuestionSet) -> dict:
    return {
        "id": qset.pk,
        "question_bank_id": qset.question_bank_id,
        "set_number": qset.set_number,
        "set_type": qset.set_type,
        "title": qset.title,
        "description": qset.description,
        "status": qset.status,
        "question_count": qset.question_count,
        "course": qset.course,
    }


def _question_dict(q: Question) -> dict:
    return {
        "id": q.pk,
        "question_number": q.question_number,
        "question_type": q.question_type,
        "prompt": q.prompt,
        "options": q.options,
        "correct_index": q.correct_index,
        "explanation": q.explanation,
        "difficulty": q.difficulty,
        "source_evidence": q.source_evidence,
        "source_excerpt": q.source_excerpt,
        "scenario_data": q.scenario_data,
        "generated_by_ai": q.generated_by_ai,
        "manually_edited": q.manually_edited,
    }


@staff_member_required
@require_http_methods(["GET", "POST"])
def question_bank_list_create(request):
    if request.method == "GET":
        banks = QuestionBank.objects.all()[:200]
        return JsonResponse({"results": [_bank_dict(b) for b in banks]})

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    bank = QuestionBank(
        title=data.get("title") or "Untitled Bank",
        description=data.get("description") or "",
        domain=data.get("domain") or "phishing_simulator",
        source_content=data.get("source_content") or "",
        source_language=data.get("source_language") or QuestionBank.LANG_SAME,
        output_language=data.get("output_language") or QuestionBank.LANG_EN,
        difficulty=data.get("difficulty") or QuestionBank.DIFF_MIXED,
        total_sets=int(data.get("total_sets") or 10),
        normal_sets=int(data.get("normal_sets") or 7),
        simulation_sets=int(data.get("simulation_sets") or 3),
        questions_per_set=int(data.get("questions_per_set") or 10),
        created_by=request.user,
    )
    try:
        bank.full_clean()
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    bank.save()
    return JsonResponse(_bank_dict(bank), status=201)


@staff_member_required
@require_http_methods(["GET"])
def question_bank_detail(request, bank_id: int):
    bank = get_object_or_404(QuestionBank, pk=bank_id)
    return JsonResponse(_bank_dict(bank))


@staff_member_required
@require_http_methods(["POST"])
def question_bank_generate(request, bank_id: int):
    bank = get_object_or_404(QuestionBank, pk=bank_id)
    updated = generate_question_bank(bank.pk, created_by=request.user)
    status_code = 200 if updated.status == QuestionBank.STATUS_REVIEW else 400
    return JsonResponse(_bank_dict(updated), status=status_code)


@staff_member_required
@require_http_methods(["GET"])
def question_bank_sets(request, bank_id: int):
    bank = get_object_or_404(QuestionBank, pk=bank_id)
    sets = QuestionSet.objects.filter(question_bank=bank).order_by("set_number")
    return JsonResponse({"results": [_set_dict(s) for s in sets]})


@staff_member_required
@require_http_methods(["GET"])
def question_set_questions(request, set_id: int):
    qset = get_object_or_404(QuestionSet, pk=set_id)
    questions = qset.ordered_questions()
    return JsonResponse({
        "set": _set_dict(qset),
        "results": [_question_dict(q) for q in questions],
    })


@staff_member_required
@require_http_methods(["POST"])
def question_set_approve(request, set_id: int):
    qset = get_object_or_404(QuestionSet, pk=set_id)
    qset.status = QuestionSet.STATUS_APPROVED
    qset.is_active = True
    qset.save(update_fields=["status", "is_active", "updated_at"])
    return JsonResponse(_set_dict(qset))


@staff_member_required
@require_http_methods(["POST"])
def question_set_reject(request, set_id: int):
    qset = get_object_or_404(QuestionSet, pk=set_id)
    qset.status = QuestionSet.STATUS_REJECTED
    qset.is_active = False
    qset.save(update_fields=["status", "is_active", "updated_at"])
    return JsonResponse(_set_dict(qset))
