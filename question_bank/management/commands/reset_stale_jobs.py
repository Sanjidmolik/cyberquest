"""Management command: mark stale GENERATING question banks as failed.

Usage:
    python manage.py reset_stale_jobs            # default: older than 10 minutes
    python manage.py reset_stale_jobs --minutes 30
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from question_bank.models import QuestionBank


class Command(BaseCommand):
    help = "Mark GENERATING question banks that have been running too long as failed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--minutes",
            type=int,
            default=10,
            help="Consider a job stale if it has been generating for more than N minutes (default 10).",
        )

    def handle(self, *args, **options):
        minutes = options["minutes"]
        cutoff = timezone.now() - timezone.timedelta(minutes=minutes)
        stale_qs = QuestionBank.objects.filter(
            status=QuestionBank.STATUS_GENERATING,
            updated_at__lt=cutoff,
        )
        count = stale_qs.count()
        if count == 0:
            self.stdout.write("No stale jobs found.")
            return
        stale_qs.update(
            status=QuestionBank.STATUS_FAILED,
            generation_stage="Generation interrupted",
            last_error=f"Job was still generating after {minutes} minutes and was reset by reset_stale_jobs.",
        )
        self.stdout.write(self.style.SUCCESS(f"Reset {count} stale job(s) to failed."))
