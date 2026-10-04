"""Django admin for AI Question Banks."""

from __future__ import annotations

import logging

from django.contrib import admin, messages
from django.utils.html import format_html

from games.models import Question, QuestionSet
from question_bank.models import QuestionBank
from question_bank.services.jobs import start_generation

logger = logging.getLogger(__name__)


class QuestionSetInline(admin.TabularInline):
    model = QuestionSet
    extra = 0
    fields = (
        "set_number", "set_type", "title", "status", "is_active",
        "question_count_display", "version",
    )
    readonly_fields = (
        "set_number", "set_type", "title", "question_count_display", "version",
    )
    show_change_link = True
    can_delete = False

    @admin.display(description="Questions")
    def question_count_display(self, obj):
        if not obj.pk:
            return "—"
        return f"{obj.question_count}/{obj.expected_question_count}"


@admin.register(QuestionBank)
class QuestionBankAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "domain",
        "status_badge",
        "total_sets",
        "normal_sets",
        "simulation_sets",
        "questions_per_set",
        "created_by",
        "created_at",
        "generated_at",
    )
    list_filter = ("domain", "status", "difficulty", "output_language")
    search_fields = ("title", "description", "source_content")

    class Media:
        css = {"all": ("question_bank/loader.css",)}
        js = ("question_bank/loader.js",)
    readonly_fields = (
        "status",
        "ai_provider",
        "ai_model",
        "generation_version",
        "last_error",
        "created_by",
        "created_at",
        "updated_at",
        "generated_at",
    )
    actions = [
        "generate_with_gemini",
        "approve_selected_banks",
        "archive_selected_banks",
    ]
    inlines = [QuestionSetInline]
    fieldsets = (
        (None, {
            "fields": ("title", "description", "domain", "difficulty"),
        }),
        ("Source content", {
            "fields": ("source_content", "source_language", "output_language"),
            "description": (
                "The AI must generate questions ONLY from this source. "
                "Output language is the target language for questions. "
                "Choose English even when the source is Bangla. "
                "Gemini must not switch that target to Hindi."
            ),
        }),
        ("Generation configuration (Customize Set)", {
            "fields": (
                "total_sets", "normal_sets", "simulation_sets", "questions_per_set",
            ),
            "description": (
                "Bank generation layout. Example: total_sets=1, normal_sets=1, "
                "simulation_sets=0, questions_per_set=5, difficulty=Mixed → "
                "2 Beginner + 2 Intermediate + 1 Advanced per generated set."
            ),
        }),
        ("Student attempt mix (difficulty × type)", {
            "fields": (
                "attempt_question_count",
                "attempt_mcq_count",
                "attempt_simulation_count",
            ),
            "description": (
                "Independent of generation set layout. Example for 5 questions: "
                "MCQ=2, Simulation=3 with Mixed difficulty → CyberQuest pairs "
                "difficulty slots with these types. Shortage of e.g. Advanced "
                "Simulation will block play (no silent substitution)."
            ),
        }),
        ("Status & provenance", {
            "fields": (
                "status", "last_error", "ai_provider", "ai_model",
                "generation_version", "created_by", "created_at",
                "updated_at", "generated_at",
            ),
        }),
    )

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            QuestionBank.STATUS_DRAFT: "#6c757d",
            QuestionBank.STATUS_GENERATING: "#0d6efd",
            QuestionBank.STATUS_REVIEW: "#fd7e14",
            QuestionBank.STATUS_PARTIAL: "#d63384",
            QuestionBank.STATUS_APPROVED: "#198754",
            QuestionBank.STATUS_FAILED: "#dc3545",
            QuestionBank.STATUS_ARCHIVED: "#6c757d",
        }
        color = colors.get(obj.status, "#333")
        return format_html(
            '<span style="color:{};font-weight:700;">{}</span>',
            color,
            obj.status,
        )

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Generate Question Bank with Gemini")
    def generate_with_gemini(self, request, queryset):
        started = []
        for bank in queryset:
            try:
                if start_generation(bank.pk, request.user.pk):
                    started.append(str(bank.pk))
                    self.message_user(
                        request,
                        f"«{bank.title}»: generation started. This page shows live status.",
                        messages.SUCCESS,
                    )
                else:
                    self.message_user(
                        request,
                        f"«{bank.title}» is already generating.",
                        messages.WARNING,
                    )
            except Exception:
                logger.exception("Admin generate failed bank_id=%s", bank.pk)
                self.message_user(
                    request,
                    f"«{bank.title}»: unexpected generation error.",
                    messages.ERROR,
                )
        if started:
            from django.http import HttpResponseRedirect
            from django.urls import reverse
            url = reverse("admin:question_bank_questionbank_changelist")
            return HttpResponseRedirect(f"{url}?generating={','.join(started)}")

    @admin.action(description="Approve selected Question Banks")
    def approve_selected_banks(self, request, queryset):
        for bank in queryset:
            if bank.status not in {
                QuestionBank.STATUS_REVIEW,
                QuestionBank.STATUS_APPROVED,
            }:
                self.message_user(
                    request,
                    f"«{bank.title}» cannot be approved from status {bank.status}. "
                    "Complete generation to REVIEW first (PARTIAL/FAILED are not approvable).",
                    messages.WARNING,
                )
                continue
            bank.status = QuestionBank.STATUS_APPROVED
            bank.save(update_fields=["status", "updated_at"])
            # Approve all REVIEW sets under this bank
            updated = QuestionSet.objects.filter(
                question_bank=bank,
                status=QuestionSet.STATUS_REVIEW,
            ).update(status=QuestionSet.STATUS_APPROVED)
            logger.info("Question bank approved bank_id=%s sets_approved=%s", bank.pk, updated)
            self.message_user(
                request,
                f"«{bank.title}» approved ({updated} sets moved to APPROVED).",
                messages.SUCCESS,
            )

    @admin.action(description="Archive selected Question Banks")
    def archive_selected_banks(self, request, queryset):
        count = queryset.update(status=QuestionBank.STATUS_ARCHIVED)
        self.message_user(request, f"Archived {count} question bank(s).", messages.SUCCESS)


# Enhance games Question / QuestionSet admin listings for bank fields via monkey patch? 
# Prefer updating games/admin.py instead.
