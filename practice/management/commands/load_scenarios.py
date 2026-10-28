"""Load interactive practice scenarios from practice/scenario_content/*.json.

Idempotent: scenarios are matched by slug and updated in place. The version goes up
whenever the content changes, so attempts can tell which content they were played on.
Rows edited or published in the Practice Studio are never touched (practice/seeding.py),
unless named with `--force SLUG ...`.
Each file names its course by `topic` (a Course.code, e.g. "MOD-01"); files whose
course does not exist yet are skipped with a warning (run sync_curriculum first).
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from courses.models import Course
from practice.graders import FLOWS, validate_content
from practice.seeding import seed_scenario

CONTENT_DIR = Path(__file__).resolve().parents[2] / "scenario_content"
REQUIRED = ("slug", "topic", "kind", "title", "difficulty", "est_minutes", "xp_reward", "content")


class Command(BaseCommand):
    help = "Load interactive practice scenarios from practice/scenario_content/*.json."

    def add_arguments(self, parser):
        parser.add_argument("--dir", default=str(CONTENT_DIR), help="Folder of scenario JSON files.")
        parser.add_argument("--force", nargs="+", metavar="SLUG", default=[],
                            help="Overwrite these scenarios even if they were edited in the Practice Studio.")

    def handle(self, *args, **options):
        folder = Path(options["dir"])
        files = sorted(folder.glob("*.json"))
        if not files:
            raise CommandError(f"No scenario files found in {folder}")

        force = set(options["force"])
        counts = {"create": 0, "update": 0, "unchanged": 0, "skip": 0}
        loaded = []
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

            loaded.append((path, data))
        unknown = force - {data["slug"] for _, data in loaded}
        if unknown:
            raise CommandError(f"--force names unknown scenarios: {', '.join(sorted(unknown))}")

        for path, data in loaded:
            course = Course.objects.filter(code=data["topic"]).first()
            if course is None:
                counts["skip"] += 1
                self.stderr.write(self.style.WARNING(f"{path.name}: no course with code {data['topic']}, skipped"))
                continue
            action, detail = seed_scenario({**data, "time_limit_sec": data.get("time_limit_sec")}, course, force=force)
            counts[action] += 1
            if action == "skip":
                self.stderr.write(self.style.WARNING(f"skip   {data['slug']}: {detail}"))

        self.stdout.write(self.style.SUCCESS(
            f"Scenarios: {counts['create']} created, {counts['update']} updated, "
            f"{counts['unchanged']} unchanged, {counts['skip']} skipped."
        ))
