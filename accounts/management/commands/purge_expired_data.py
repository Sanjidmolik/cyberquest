"""Apply the documented retention periods (accounts/retention.py).

Safe to schedule (for example a daily Render cron job). Only expired or
abandoned data is touched, and a second run right after the first does nothing.
"""

from django.core.management.base import BaseCommand

from accounts.retention import run_all


class Command(BaseCommand):
    help = "Remove expired verification codes, sessions, cache entries and abandoned sign-ups."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report counts without deleting.")

    def handle(self, *args, dry_run=False, **options):
        results = run_all(dry_run=dry_run)
        prefix = "[dry run] would remove" if dry_run else "removed"
        for name, count in results.items():
            self.stdout.write(f"{prefix} {count} {name.replace('_', ' ')}")
