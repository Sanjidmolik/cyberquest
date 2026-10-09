"""
Copy the Git-tracked course PDFs and certificate designs onto MEDIA_ROOT.

Run once by hand after MEDIA_ROOT points at a persistent disk. This command
is not called from startup or the deploy script. Existing destination files
are left untouched.
"""

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

# Repository-relative names. Do not expand this list to every file under media/.
SEED_FILES = (
    "course_ebooks/The_Phishing_Detectives_Handbook.pdf",
    "course_ebooks/course1.pdf",
    "certificate_templates/CyberQuest_Certificate_of_Achievement.pdf",
    "certificate_templates/a.pdf",
    "certificate_templates/b.pdf",
    "certificate_templates/bg.jpg",
    "certificate_templates/design.png",
    "certificate_templates/new.png",
)


class Command(BaseCommand):
    help = "Copy the eight Git-tracked course and certificate files onto MEDIA_ROOT if they are absent."

    def handle(self, *args, **options):
        source_root = Path(settings.BASE_DIR) / "media"
        dest_root = Path(settings.MEDIA_ROOT).resolve()
        copied = 0
        skipped = 0
        for relative in SEED_FILES:
            source = source_root / relative
            destination = dest_root / relative
            if destination.exists():
                skipped += 1
                self.stdout.write(f"skip {relative}")
                continue
            if not source.is_file():
                self.stdout.write(f"missing source {relative}")
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            copied += 1
            self.stdout.write(f"copied {relative}")
        self.stdout.write(self.style.SUCCESS(f"Seed finished. Copied {copied}, left {skipped} existing files."))
