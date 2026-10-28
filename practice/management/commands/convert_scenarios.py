"""Convert every original practice scenario into an interactive Scenario row.

Idempotent: rows are matched by slug (the old key with hyphens) and only written when the
converted content or fields differ; the version goes up when content changes.
`--dry-run` prints what would be created or updated and writes nothing.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from courses.models import Course
from practice.conversion import convert
from practice.graders import validate_content
from practice.models import Scenario
from practice.scenarios import SCENARIOS

FIELDS = ("kind", "title", "difficulty", "est_minutes", "time_limit_sec", "xp_reward")


class Command(BaseCommand):
    help = "Convert every original practice scenario into the interactive step format."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing.")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        courses = {c.code: c for c in Course.objects.all()}
        counts = {"create": 0, "update": 0, "unchanged": 0, "skipped": 0}

        for key, old in SCENARIOS.items():
            data = convert(old)
            validate_content(data["kind"], data["content"])
            flow = " -> ".join(step["type"] for step in data["content"]["steps"])
            course = courses.get(data["topic"])
            if course is None:
                counts["skipped"] += 1
                self.stderr.write(self.style.WARNING(f"skip   {data['slug']}: no course {data['topic']} (run sync_curriculum)"))
                continue

            row = Scenario.objects.filter(slug=data["slug"]).first()
            if row is None:
                counts["create"] += 1
                self.stdout.write(f"create {data['slug']:32} {data['topic']:12} {data['kind']:10} {flow}")
                if not dry:
                    Scenario.objects.create(slug=data["slug"], topic=course, content=data["content"],
                                            **{f: data[f] for f in FIELDS})
                continue

            changed = [f for f in FIELDS if getattr(row, f) != data[f]]
            if row.topic_id != course.pk:
                changed.append("topic")
            if row.content != data["content"]:
                changed.append("content")
            if not changed:
                counts["unchanged"] += 1
                continue
            counts["update"] += 1
            self.stdout.write(f"update {data['slug']:32} {', '.join(changed)}")
            if not dry:
                with transaction.atomic():
                    if "content" in changed:
                        row.content = data["content"]
                        row.version += 1
                    row.topic = course
                    for f in FIELDS:
                        setattr(row, f, data[f])
                    row.save()

        prefix = "Dry run: would " if dry else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}create {counts['create']}, update {counts['update']}, "
            f"leave {counts['unchanged']} unchanged, skip {counts['skipped']}."
        ))
