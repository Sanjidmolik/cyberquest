from django.contrib import admin, messages
from django.utils.html import format_html

from .models import GameAttempt, Question, QuestionSet, QuestionSetItem, QUESTIONS_PER_SET
from .question_sets import regenerate_auto_sets, ensure_set_slots


@admin.register(GameAttempt)
class GameAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "user", "game_key", "set_number", "score", "total_questions",
        "xp_awarded", "completed_at",
    )
    list_filter = ("game_key", "set_number")
    readonly_fields = ("completed_at",)


class QuestionSetItemInline(admin.TabularInline):
    model = QuestionSetItem
    extra = 0
    autocomplete_fields = ("question",)
    ordering = ("order",)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        "id", "course", "question_type", "difficulty", "short_prompt",
        "correct_index", "generated_by_ai", "manually_edited", "is_active", "updated_at",
    )
    list_filter = ("course", "question_type", "difficulty", "generated_by_ai", "manually_edited", "is_active")
    search_fields = ("prompt", "source_evidence", "explanation")
    list_editable = ("is_active",)
    readonly_fields = ("generated_by_ai", "manually_edited", "created_at", "updated_at")

    @admin.display(description="Prompt")
    def short_prompt(self, obj):
        return (obj.prompt[:80] + "…") if len(obj.prompt) > 80 else obj.prompt


@admin.register(QuestionSet)
class QuestionSetAdmin(admin.ModelAdmin):
    list_display = (
        "course", "set_number", "set_type", "status_badge", "bank_link",
        "question_count_display", "readiness_display", "is_active", "version", "updated_at",
    )
    list_filter = ("course", "set_type", "status", "is_active", "question_bank")
    search_fields = ("title", "description")
    inlines = [QuestionSetItemInline]
    actions = [
        "regenerate_selected_auto_sets",
        "ensure_all_slots",
        "approve_selected_sets",
        "reject_selected_sets",
    ]
    readonly_fields = ("version", "created_at", "updated_at", "readiness_display")
    raw_id_fields = ("question_bank",)

    def get_queryset(self, request):
        ensure_set_slots()
        return super().get_queryset(request).select_related("question_bank").prefetch_related("items")

    @admin.display(description="Questions")
    def question_count_display(self, obj):
        return f"{obj.question_count} / {obj.expected_question_count}"

    @admin.display(description="Bank")
    def bank_link(self, obj):
        if not obj.question_bank_id:
            return "—"
        return obj.question_bank.title[:40]

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            QuestionSet.STATUS_DRAFT: "#6c757d",
            QuestionSet.STATUS_REVIEW: "#fd7e14",
            QuestionSet.STATUS_APPROVED: "#198754",
            QuestionSet.STATUS_REJECTED: "#dc3545",
        }
        return format_html(
            '<span style="color:{};font-weight:700;">{}</span>',
            colors.get(obj.status, "#333"),
            obj.status,
        )

    @admin.display(description="Readiness")
    def readiness_display(self, obj):
        status = obj.readiness
        if status == "READY":
            return format_html(
                '<span style="color:#1a7f37;font-weight:700;">{}</span>',
                "READY ✓",
            )
        if status == "INVALID":
            return format_html(
                '<span style="color:#cf222e;font-weight:700;">INVALID (&gt;{})</span>',
                obj.expected_question_count,
            )
        return format_html(
            '<span style="color:#9a6700;font-weight:700;">{}</span>',
            "INCOMPLETE ⚠",
        )

    @admin.action(description="Approve selected Question Sets")
    def approve_selected_sets(self, request, queryset):
        count = queryset.update(status=QuestionSet.STATUS_APPROVED)
        self.message_user(request, f"Approved {count} set(s).", messages.SUCCESS)

    @admin.action(description="Reject selected Question Sets")
    def reject_selected_sets(self, request, queryset):
        count = queryset.update(status=QuestionSet.STATUS_REJECTED, is_active=False)
        self.message_user(request, f"Rejected {count} set(s).", messages.WARNING)

    @admin.action(description="Regenerate AUTO sets for selected courses")
    def regenerate_selected_auto_sets(self, request, queryset):
        courses = set(queryset.filter(set_type=QuestionSet.SET_TYPE_AUTO).values_list("course", flat=True))
        if not courses:
            self.message_user(request, "Select at least one AUTO set (or any set from the target course).", messages.WARNING)
            return
        for course in courses:
            result = regenerate_auto_sets(course)
            if result["ok"]:
                self.message_user(request, f"{course}: regenerated 7 AUTO sets.", messages.SUCCESS)
            else:
                self.message_user(request, f"{course}: {result['warning']}", messages.ERROR)

    @admin.action(description="Ensure all 10 set slots exist for every course")
    def ensure_all_slots(self, request, queryset):
        ensure_set_slots()
        self.message_user(request, "All course set slots verified (3 ADMIN + 7 AUTO).", messages.SUCCESS)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if obj.set_type == QuestionSet.SET_TYPE_ADMIN:
            count = obj.question_count
            needed = obj.expected_question_count
            if count > needed:
                self.message_user(
                    request,
                    f"Admin Set {obj.set_number} has {count} questions — INVALID (must be exactly {needed}).",
                    messages.ERROR,
                )
            elif count < needed:
                self.message_user(
                    request,
                    f"Admin Set {obj.set_number}: {count}/{needed} — INCOMPLETE (not usable yet).",
                    messages.WARNING,
                )
            else:
                self.message_user(
                    request,
                    f"Admin Set {obj.set_number}: {needed}/{needed} — READY ✓",
                    messages.SUCCESS,
                )
