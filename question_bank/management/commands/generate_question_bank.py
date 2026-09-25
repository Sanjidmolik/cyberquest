from django.core.management.base import BaseCommand, CommandError

from question_bank.models import QuestionBank
from question_bank.services.generator import generate_question_bank


class Command(BaseCommand):
    help = "Generate (or regenerate) an AI Question Bank by id using the configured provider."

    def add_arguments(self, parser):
        parser.add_argument("bank_id", type=int, help="QuestionBank primary key")

    def handle(self, *args, **options):
        bank_id = options["bank_id"]
        try:
            QuestionBank.objects.get(pk=bank_id)
        except QuestionBank.DoesNotExist as exc:
            raise CommandError(f"QuestionBank id={bank_id} does not exist.") from exc

        self.stdout.write(f"Generating question bank id={bank_id} …")
        bank = generate_question_bank(bank_id)
        if bank.status == QuestionBank.STATUS_REVIEW:
            self.stdout.write(self.style.SUCCESS(
                f"OK — {bank.total_sets} sets / {bank.expected_total_questions} questions "
                f"(status={bank.status})."
            ))
        else:
            raise CommandError(bank.last_error or f"Generation failed (status={bank.status}).")
