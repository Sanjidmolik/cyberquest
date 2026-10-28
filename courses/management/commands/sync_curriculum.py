"""Apply courses/curriculum.py to the database. Idempotent; runs on every deploy."""

from django.core.management.base import BaseCommand
from django.db import transaction

from courses.curriculum import sync_curriculum
from courses.models import ChapterQuestion, Chapter, ComicPanel, Course


class Command(BaseCommand):
    help = "Create or update the eight defence courses and lock the Coming Soon courses."

    def handle(self, *args, **options):
        with transaction.atomic():
            sync_curriculum(Course, Chapter, ComicPanel, ChapterQuestion, log=self.stdout.write)
        self.stdout.write(self.style.SUCCESS("Curriculum is in sync."))
