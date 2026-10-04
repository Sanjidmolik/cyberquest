"""Abstract AI provider interface for question-bank generation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AIQuestionProvider(ABC):
    """Provider-independent interface for generating / repairing question banks."""

    @abstractmethod
    def generate_question_bank(
        self,
        *,
        source_content: str,
        domain: str,
        language: str,
        difficulty: str,
        total_sets: int,
        normal_sets: int,
        simulation_sets: int,
        questions_per_set: int,
        set_plans: list[dict[str, Any]] | None = None,
        target_language: str | None = None,
        source_language: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def generate_replacements(
        self,
        *,
        source_content: str,
        domain: str,
        language: str,
        missing_slots: list[dict[str, Any]],
        existing_questions: list[dict[str, Any]],
        target_language: str | None = None,
        source_language: str | None = None,
    ) -> dict[str, Any]:
        """Optional repair API. Default raises if not implemented."""
        raise NotImplementedError("This provider does not support replacement generation.")
