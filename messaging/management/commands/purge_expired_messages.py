"""Delete expired disappearing messages and their photo files for good.

Safe to run every minute and to run twice: it only removes what has already expired, and
expired messages are hidden from every page and API before this runs. Logs counts only.
Scheduling: see DEPLOYMENT.md ("Disappearing messages cleanup").
"""

from django.core.management.base import BaseCommand

from messaging.expiry import purge


class Command(BaseCommand):
    help = "Delete expired disappearing messages and their photo files."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count what would be deleted; delete nothing.")

    def handle(self, *args, **options):
        done = purge(dry_run=options["dry_run"])
        verb = "Would delete" if options["dry_run"] else "Deleted"
        self.stdout.write(f"{verb} {done['messages']} expired messages and {done['photo_files']} photo files.")
