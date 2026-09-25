"""
AI-powered Question Bank metadata.

Generated QuestionSet / Question rows live in the existing games app and
link back here via QuestionSet.question_bank.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from games.models import SET_COURSES


class QuestionBank(models.Model):
    """Admin-authored learning source + generation configuration."""

    STATUS_DRAFT = "DRAFT"
    STATUS_GENERATING = "GENERATING"
    STATUS_REVIEW = "REVIEW"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_APPROVED = "APPROVED"
    STATUS_ARCHIVED = "ARCHIVED"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_GENERATING, "Generating"),
        (STATUS_REVIEW, "Ready for review"),
        (STATUS_PARTIAL, "Partial — needs repair"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_ARCHIVED, "Archived"),
        (STATUS_FAILED, "Failed"),
    ]

    LANG_SAME = "same_as_source"
    LANG_EN = "en"
    LANG_BN = "bn"
    LANGUAGE_CHOICES = [
        (LANG_SAME, "Same as Source"),
        (LANG_EN, "English"),
        (LANG_BN, "বাংলা"),
    ]

    DIFF_BEGINNER = "beginner"
    DIFF_INTERMEDIATE = "intermediate"
    DIFF_ADVANCED = "advanced"
    DIFF_MIXED = "mixed"
    DIFFICULTY_CHOICES = [
        (DIFF_BEGINNER, "Beginner"),
        (DIFF_INTERMEDIATE, "Intermediate"),
        (DIFF_ADVANCED, "Advanced"),
        (DIFF_MIXED, "Mixed"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    domain = models.CharField(max_length=50, choices=SET_COURSES, db_index=True)
    source_content = models.TextField(
        help_text="Only knowledge source for AI generation. Stored as a snapshot.",
    )
    source_language = models.CharField(
        max_length=20,
        choices=LANGUAGE_CHOICES,
        default=LANG_SAME,
    )
    output_language = models.CharField(
        max_length=20,
        choices=LANGUAGE_CHOICES,
        default=LANG_SAME,
    )
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        default=DIFF_MIXED,
        help_text=(
            "Customize Set difficulty mode. "
            "Mixed → CyberQuest balanced blueprint. "
            "Beginner/Intermediate/Advanced → all questions that level."
        ),
    )
    total_sets = models.PositiveSmallIntegerField(default=10)
    normal_sets = models.PositiveSmallIntegerField(default=7)
    simulation_sets = models.PositiveSmallIntegerField(default=3)
    questions_per_set = models.PositiveSmallIntegerField(
        default=10,
        help_text=(
            "Customize Set: number of questions per generated set. "
            "With difficulty=Mixed and 5 questions → 2 Beginner + 2 Intermediate + 1 Advanced."
        ),
    )
    # Student attempt mix (independent of generation set layout)
    attempt_question_count = models.PositiveSmallIntegerField(
        default=5,
        help_text="Questions shown per student attempt when using balanced selection.",
    )
    attempt_mcq_count = models.PositiveSmallIntegerField(
        default=2,
        help_text="MCQ slots per attempt (must sum with simulations to attempt_question_count).",
    )
    attempt_simulation_count = models.PositiveSmallIntegerField(
        default=3,
        help_text="Simulation slots per attempt (independent of difficulty labels).",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )
    ai_provider = models.CharField(max_length=50, blank=True, default="")
    ai_model = models.CharField(max_length=100, blank=True, default="")
    generation_version = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="question_banks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    generated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Question Bank"
        verbose_name_plural = "Question Banks"

    def __str__(self) -> str:
        return f"{self.title} ({self.get_domain_display()}) [{self.status}]"

    def clean(self):
        errors = {}
        if self.total_sets < 1:
            errors["total_sets"] = "Must be at least 1."
        if self.questions_per_set < 1:
            errors["questions_per_set"] = "Must be at least 1."
        if self.normal_sets + self.simulation_sets != self.total_sets:
            errors["total_sets"] = (
                "normal_sets + simulation_sets must equal total_sets."
            )
        if self.attempt_question_count < 1:
            errors["attempt_question_count"] = "Must be at least 1."
        if (
            self.attempt_mcq_count + self.attempt_simulation_count
            != self.attempt_question_count
        ):
            errors["attempt_question_count"] = (
                "attempt_mcq_count + attempt_simulation_count must equal "
                "attempt_question_count."
            )
        if not (self.source_content or "").strip():
            errors["source_content"] = "Source content is required."
        if errors:
            raise ValidationError(errors)

    @property
    def expected_total_questions(self) -> int:
        return self.total_sets * self.questions_per_set

    def resolve_output_language(self) -> str:
        """Return concrete language code for generation prompts."""
        if self.output_language == self.LANG_SAME:
            if self.source_language == self.LANG_BN:
                return self.LANG_BN
            return self.LANG_EN
        return self.output_language
