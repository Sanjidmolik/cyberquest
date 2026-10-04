"""Background generation without a task queue.

Question generation stays a normal function for tests and the API.
The admin UI starts it in a daemon thread and polls stage fields on
QuestionBank so the browser can show real status without a percentage.
"""

from __future__ import annotations

import logging
import threading

from question_bank.models import QuestionBank

logger = logging.getLogger(__name__)


def start_generation(bank_id: int, user_id: int | None) -> bool:
    """
    Mark the bank as generating and run generate_question_bank in a thread.

    Returns False when a run is already in progress.
    """
    bank = QuestionBank.objects.get(pk=bank_id)
    if bank.status == QuestionBank.STATUS_GENERATING:
        return False
    bank.status = QuestionBank.STATUS_GENERATING
    bank.generation_stage = "Analyzing source material..."
    bank.generation_completed = 0
    bank.generation_requested = bank.expected_total_questions
    bank.last_error = ""
    bank.save(update_fields=[
        "status", "generation_stage", "generation_completed",
        "generation_requested", "last_error", "updated_at",
    ])

    def _run():
        from django.db import connection
        from question_bank.services.generator import generate_question_bank
        from django.contrib.auth import get_user_model

        try:
            user = None
            if user_id:
                user = get_user_model().objects.filter(pk=user_id).first()
            generate_question_bank(bank_id, created_by=user)
        except Exception:
            logger.exception("Background generation crashed bank_id=%s", bank_id)
            QuestionBank.objects.filter(pk=bank_id).update(
                status=QuestionBank.STATUS_FAILED,
                generation_stage="Generation failed",
                last_error="Question generation failed: unexpected server error.",
            )
        finally:
            connection.close()

    threading.Thread(target=_run, daemon=True, name=f"qbank-{bank_id}").start()
    return True
