"""Load interactive practice scenarios from practice/scenario_content/*.json.

Idempotent: scenarios are matched by slug and updated in place. The version goes up
whenever the content changes, so attempts can tell which content they were played on.
Each file names its course by `topic` (a Course.code, e.g. "MOD-01"); files whose
course does not exist yet are skipped with a warning (run sync_curriculum first).
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from courses.models import Course
from practice.graders import FLOWS, validate_content
from practice.models import Scenario

CONTENT_DIR = Path(__file__).resolve().parents[2] / "scenario_content"
REQUIRED = ("slug", "topic", "kind", "title", "difficulty", "est_minutes", "xp_reward", "content")


class Command(BaseCommand):
    help = "Load interactive practice scenarios from practice/scenario_content/*.json."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=str(CONTENT_DIR), help="Folder of scenario JSON files.")

    def handle(self, *args, **options):
        folder = Path(options["dir"])
        files = sorted(folder.glob("*.json"))
        if not files:
            raise CommandError(f"No scenario files found in {folder}")

        created = updated = unchanged = skipped = 0
        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                missing = [k for k in REQUIRED if k not in data]
                if missing:
                    raise ValueError(f"missing {', '.join(missing)}")
                if data["kind"] not in FLOWS:
                    raise ValueError(f"unknown kind {data['kind']!r}")
                validate_content(data["kind"], data["content"])
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                raise CommandError(f"{path.name}: {exc}") from exc

            course = Course.objects.filter(code=data["topic"]).first()
            if course is None:
                skipped += 1
                self.stderr.write(self.style.WARNING(f"{path.name}: no course with code {data['topic']}, skipped"))
                continue

            fields = {
                "topic": course,
                "kind": data["kind"],
                "title": data["title"],
                "difficulty": data["difficulty"],
                "est_minutes": data["est_minutes"],
                "time_limit_sec": data.get("time_limit_sec"),
                "xp_reward": data["xp_reward"],
            }
            with transaction.atomic():
                scenario = Scenario.objects.select_for_update().filter(slug=data["slug"]).first()
                if scenario is None:
                    Scenario.objects.create(slug=data["slug"], content=data["content"], **fields)
                    created += 1
                    continue
                changed = scenario.content != data["content"]
                if changed:
                    scenario.content = data["content"]
                    scenario.version += 1
                for name, value in fields.items():
                    if getattr(scenario, name) != value:
                        setattr(scenario, name, value)
                        changed = True
                if changed:
                    scenario.save()
                    updated += 1
                else:
                    unchanged += 1

        self.stdout.write(self.style.SUCCESS(
            f"Scenarios: {created} created, {updated} updated, {unchanged} unchanged, {skipped} skipped."
        ))
