"""
Seed question pool, ensure 10 set slots, populate ADMIN sets 1-3 and AUTO 4-10.
Idempotent: safe to re-run.
"""

from django.core.management.base import BaseCommand

from games.models import (
    ADMIN_SET_NUMBERS,
    QUESTIONS_PER_SET,
    SET_COURSE_KEYS,
    Question,
    QuestionSet,
)
from games.question_sets import assign_questions_to_set, ensure_set_slots, regenerate_auto_sets
from games.seed_pool import iter_seed_questions


class Command(BaseCommand):
    help = "Seed question pools and initialize 3 ADMIN + 7 AUTO question sets per course."

    def add_arguments(self, parser):
        parser.add_argument(
            "--regen-auto",
            action="store_true",
            help="Force regenerate AUTO sets even if already filled.",
        )

    def handle(self, *args, **options):
        created_q = 0
        for data in iter_seed_questions():
            obj, was = Question.objects.get_or_create(
                course=data["course"],
                prompt=data["prompt"],
                defaults={
                    "options": data["options"],
                    "correct_index": data["correct_index"],
                    "explanation": data["explanation"],
                    "correct_feedback": data.get("correct_feedback", "Correct!"),
                    "wrong_feedback": data.get("wrong_feedback", ""),
                    "is_active": True,
                },
            )
            if was:
                created_q += 1

        ensure_set_slots()
        self.stdout.write(self.style.SUCCESS(f"Questions created: {created_q} (pool total {Question.objects.count()})"))

        for course in SET_COURSE_KEYS:
            # Fill empty ADMIN sets from first unused pool questions
            used_ids = set(
                Question.objects.filter(sets__course=course, sets__set_type=QuestionSet.SET_TYPE_ADMIN)
                .values_list("id", flat=True)
            )
            pool = list(Question.objects.filter(course=course, is_active=True).order_by("id"))
            for num in ADMIN_SET_NUMBERS:
                qs = QuestionSet.objects.get(
                    course=course, set_number=num, question_bank__isnull=True,
                )
                if qs.question_count >= QUESTIONS_PER_SET:
                    continue
                available = [q for q in pool if q.id not in used_ids]
                if len(available) < QUESTIONS_PER_SET:
                    self.stdout.write(self.style.WARNING(
                        f"{course} Admin Set {num}: not enough unused questions to auto-fill."
                    ))
                    continue
                pick = available[:QUESTIONS_PER_SET]
                assign_questions_to_set(qs, pick)
                used_ids.update(q.id for q in pick)
                self.stdout.write(f"Filled ADMIN set {course} #{num}")

            auto_ready = QuestionSet.objects.filter(
                course=course, set_type=QuestionSet.SET_TYPE_AUTO, items__isnull=False
            ).distinct().count()
            if options["regen_auto"] or auto_ready < 7:
                result = regenerate_auto_sets(course)
                if result["ok"]:
                    self.stdout.write(self.style.SUCCESS(f"{course}: generated 7 AUTO sets"))
                else:
                    self.stdout.write(self.style.ERROR(f"{course}: {result['warning']}"))
            else:
                self.stdout.write(f"{course}: AUTO sets already present (use --regen-auto to rebuild)")
