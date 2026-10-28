"""Convert every original practice scenario into an interactive Scenario row.

Idempotent: rows are matched by slug (the old key with hyphens) and only written when the
converted content or fields differ; the version goes up when content changes. Rows edited
or published in the Practice Studio are never touched (practice/seeding.py), unless named
with `--force SLUG ...`. `--dry-run` prints what would change and writes nothing.
"""

from django.core.management.base import BaseCommand, CommandError

from courses.models import Course
from practice.conversion import convert
from practice.graders import validate_content
from practice.scenarios import SCENARIOS
from practice.seeding import seed_scenario


class Command(BaseCommand):
    help = "Convert every original practice scenario into the interactive step format."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing.")
        parser.add_argument("--force", nargs="+", metavar="SLUG", default=[],
                            help="Overwrite these scenarios even if they were edited in the Practice Studio.")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        force = set(options["force"])
        known = {convert(old)["slug"] for old in SCENARIOS.values()}
        if force - known:
            raise CommandError(f"--force names unknown scenarios: {', '.join(sorted(force - known))}")
        courses = {c.code: c for c in Course.objects.all()}
        counts = {"create": 0, "update": 0, "unchanged": 0, "skip": 0}

        for key, old in SCENARIOS.items():
            data = convert(old)
            validate_content(data["kind"], data["content"])
            flow = " -> ".join(step["type"] for step in data["content"]["steps"])
            course = courses.get(data["topic"])
            if course is None:
                counts["skip"] += 1
                self.stderr.write(self.style.WARNING(f"skip   {data['slug']}: no course {data['topic']} (run sync_curriculum)"))
                continue
            action, detail = seed_scenario(data, course, force=force, dry=dry)
            counts[action] += 1
            if action == "create":
                self.stdout.write(f"create {data['slug']:32} {data['topic']:12} {data['kind']:10} {flow}")
            elif action == "update":
                self.stdout.write(f"update {data['slug']:32} {detail}")
            elif action == "skip":
                self.stderr.write(self.style.WARNING(f"skip   {data['slug']}: {detail}"))

        prefix = "Dry run: would " if dry else ""
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}create {counts['create']}, update {counts['update']}, "
            f"leave {counts['unchanged']} unchanged, skip {counts['skip']}."
        ))
