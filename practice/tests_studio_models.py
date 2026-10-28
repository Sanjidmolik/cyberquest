"""Practice Studio, phase 1: status, versions, preview attempts, groups, and the seed rules
that keep deploys (build.sh) from overwriting studio work."""

import copy
import importlib
import json
import re
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import URLPattern, reverse
from django.utils import timezone

from practice.graders import ANSWER_KEYS, public_content
from practice.models import Attempt, PracticeSession, Scenario, ScenarioVersion, StudioAuditLog
from practice.seeding import content_hash
from practice.session_views import attempt_content
from practice.testing import answer_for, convert_all

User = get_user_model()
CONVERTED = "phishing-microsoft-disable"
CHOICE = "phish-01-choice"


def _run(command, *args, **kwargs):
    out, err = StringIO(), StringIO()
    call_command(command, *args, stdout=out, stderr=err, **kwargs)
    return out.getvalue(), err.getvalue()


def _snapshot():
    return {
        s.slug: (s.content, s.version, s.title, s.status, s.source, s.content_hash, s.topic_id)
        for s in Scenario.objects.all()
    }


def _publish_new_answer(row):
    """Simulate a studio publish that changes the decision's right answer. Returns the step index."""
    decide = next(i for i, s in enumerate(row.content["steps"]) if s["type"] == "mcq")
    step = row.content["steps"][decide]
    right = step["correct"][0] if isinstance(step["correct"], list) else step["correct"]
    step["correct"] = (right + 1) % len(step["options"])
    row.version += 1
    row.save()
    ScenarioVersion.objects.create(scenario=row, version=row.version, content=row.content, origin=ScenarioVersion.STUDIO)
    return decide


def _build_seed_commands():
    """The `python manage.py …` lines of build.sh that write content, in order."""
    script = (Path(settings.BASE_DIR) / "build.sh").read_text(encoding="utf-8")
    commands = re.findall(r"^python manage\.py (\S+)", script, flags=re.M)
    return [c for c in commands if c in ("sync_curriculum", "load_scenarios", "convert_scenarios")]


class SeedRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        convert_all()

    def _studio_edit(self, slug, title="Edited in the studio"):
        row = Scenario.objects.get(slug=slug)
        row.title = title
        row.content = {**row.content, "debrief": {**row.content["debrief"], "sub": "Studio text"}}
        row.source = Scenario.STUDIO
        row.save()
        return row

    def test_build_script_runs_both_seed_commands_after_the_curriculum(self):
        self.assertEqual(_build_seed_commands(), ["sync_curriculum", "load_scenarios", "convert_scenarios"])

    def test_running_the_build_twice_changes_nothing(self):
        self._studio_edit(CONVERTED)
        before = _snapshot()
        for _ in range(2):
            for command in _build_seed_commands():
                out, _err = _run(command)
                if command == "convert_scenarios":
                    self.assertIn("create 0, update 0", out)
                if command == "load_scenarios":
                    self.assertIn("0 created, 0 updated", out)
        self.assertEqual(_snapshot(), before)

    def test_missing_seed_scenarios_are_created(self):
        Scenario.objects.filter(slug=CONVERTED).delete()
        out, _ = _run("convert_scenarios")
        self.assertIn(f"create {CONVERTED}", out)
        row = Scenario.objects.get(slug=CONVERTED)
        self.assertEqual((row.source, row.status, row.content_hash), ("seed", "published", content_hash(row.content)))

    def test_seed_rows_are_updated_when_the_seed_changes(self):
        row = Scenario.objects.get(slug=CONVERTED)
        old = copy.deepcopy(row.content)
        row.content["debrief"]["sub"] = "An older seed"
        row.content_hash = content_hash(row.content)   # as if the seed itself had said this
        row.save()
        out, _ = _run("convert_scenarios")
        self.assertIn(f"update {CONVERTED}", out)   # the seed's own v1 snapshot does not block it
        row.refresh_from_db()
        self.assertEqual((row.content, row.version), (old, 2))
        self.assertEqual(list(row.versions.order_by("version").values_list("version", "origin")),
                         [(1, "seed"), (2, "seed")])

    def test_every_seed_scenario_has_a_snapshot_of_its_version(self):
        for row in Scenario.objects.all():
            snap = row.versions.get(version=row.version)
            self.assertEqual((snap.origin, snap.content), ("seed", row.content), row.slug)

    def test_fingerprint_ignores_key_order_and_whitespace(self):
        content = Scenario.objects.get(slug=CHOICE).content

        def reorder(value):
            if isinstance(value, dict):
                return {k: reorder(value[k]) for k in reversed(list(value))}
            if isinstance(value, list):
                return [reorder(v) for v in value]
            return value

        shuffled = reorder(content)
        self.assertNotEqual(json.dumps(shuffled), json.dumps(content))     # really reordered
        self.assertEqual(content_hash(shuffled), content_hash(content))
        self.assertEqual(content_hash(json.loads(json.dumps(content, indent=4))), content_hash(content))
        # A seed row whose stored JSON comes back reordered (MySQL JSON does this) is not "hand-edited".
        row = Scenario.objects.get(slug=CHOICE)
        Scenario.objects.filter(pk=row.pk).update(content=shuffled)
        _, err = _run("load_scenarios")
        self.assertNotIn("skip", err)

    def test_studio_rows_are_never_touched_and_the_skip_is_logged(self):
        row = self._studio_edit(CONVERTED)
        with self.assertLogs("practice.seeding", "WARNING") as logs:
            out, err = _run("convert_scenarios")
        self.assertIn(f"skip   {CONVERTED}: edited in the Practice Studio", err)
        self.assertIn("skip 1", out)
        self.assertTrue(any(CONVERTED in line for line in logs.output))
        fresh = Scenario.objects.get(slug=CONVERTED)
        self.assertEqual((fresh.title, fresh.content, fresh.version), (row.title, row.content, row.version))

    def test_rows_with_published_versions_are_never_touched(self):
        row = Scenario.objects.get(slug=CHOICE)
        ScenarioVersion.objects.create(scenario=row, version=row.version + 1, content=row.content,
                                       origin=ScenarioVersion.STUDIO)
        row.title = "Changed"
        row.save()   # still source "seed": the published version alone protects it
        _, err = _run("load_scenarios")
        self.assertIn(f"skip   {CHOICE}: has published studio versions", err)
        self.assertEqual(Scenario.objects.get(slug=CHOICE).title, "Changed")

    def test_hand_edited_seed_rows_are_skipped(self):
        row = Scenario.objects.get(slug=CONVERTED)
        row.content["debrief"]["sub"] = "Edited in Django admin"
        row.save()
        _, err = _run("convert_scenarios")
        self.assertIn("changed outside the seed commands", err)
        self.assertEqual(Scenario.objects.get(slug=CONVERTED).content["debrief"]["sub"], "Edited in Django admin")

    def test_force_needs_an_explicit_slug_list(self):
        with self.assertRaises(CommandError):
            _run("convert_scenarios", "--force")
        with self.assertRaises(CommandError):
            _run("load_scenarios", "--force")
        with self.assertRaises(CommandError):
            _run("convert_scenarios", "--force", "no-such-scenario")

    def test_force_overwrites_only_the_named_rows_and_audits_it(self):
        self._studio_edit(CONVERTED)
        self._studio_edit("phishing-google-login")
        out, _ = _run("convert_scenarios", "--force", CONVERTED)
        self.assertIn(f"update {CONVERTED}", out)
        forced = Scenario.objects.get(slug=CONVERTED)
        self.assertEqual((forced.source, forced.draft_content), ("seed", None))
        self.assertNotEqual(forced.title, "Edited in the studio")
        self.assertEqual(Scenario.objects.get(slug="phishing-google-login").title, "Edited in the studio")
        log = StudioAuditLog.objects.get(slug=CONVERTED)
        self.assertEqual((log.action, log.user), ("seed_force", None))

    def test_dry_run_reports_skips_and_writes_nothing(self):
        self._studio_edit(CONVERTED)
        before = _snapshot()
        out, err = _run("convert_scenarios", "--dry-run")
        self.assertIn("Dry run", out)
        self.assertIn(CONVERTED, err)
        self.assertEqual(_snapshot(), before)


class StudentVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        convert_all()
        cls.user = User.objects.create_user(email="learner@example.com", password="testpass123", username="learner")

    def setUp(self):
        self.client.force_login(self.user)

    def _start(self, slug):
        return self.client.post(reverse("practice:api_start"), json.dumps({"scenario": slug}),
                                content_type="application/json")

    def test_drafts_and_archived_scenarios_are_invisible_to_students(self):
        for status in (Scenario.DRAFT, Scenario.ARCHIVED):
            Scenario.objects.filter(slug__in=[CONVERTED, CHOICE]).update(status=status)
            for slug in (CONVERTED, CHOICE):
                self.assertEqual(self.client.get(f"/practice/{slug}/").status_code, 404)
                self.assertEqual(self._start(slug).status_code, 404)
            page = self.client.get(reverse("practice:center")).content.decode()
            self.assertNotIn(f'href="/practice/{CONVERTED}/"', page)
            self.assertNotIn(f'href="/practice/{CHOICE}/"', page)
            self.assertIn('href="/practice/phishing-google-login/"', page)

    def test_studio_edited_original_shows_its_published_title(self):
        Scenario.objects.filter(slug=CONVERTED).update(title="A brand new title", source=Scenario.STUDIO)
        self.assertContains(self.client.get(reverse("practice:center")), "A brand new title")

    def _answer(self, attempt_id, step_no, step):
        return self.client.post(reverse("practice:api_answer", args=[attempt_id]),
                                json.dumps({"step": step_no, "answer": answer_for(step)}),
                                content_type="application/json").json()

    def test_an_attempt_is_graded_on_the_version_it_started_on(self):
        start = self._start(CONVERTED).json()
        row = Scenario.objects.get(slug=CONVERTED)
        old_steps = copy.deepcopy(row.content["steps"])
        decide = _publish_new_answer(row)
        self.assertTrue(self._answer(start["attempt_id"], decide, old_steps[decide])["correct"])
        # A learner who starts now plays (and is graded on) the new version.
        fresh = self._start(CONVERTED).json()
        self.assertFalse(self._answer(fresh["attempt_id"], decide, old_steps[decide])["correct"])

    def test_attempt_started_before_this_deploy_still_grades_on_its_content(self):
        row = Scenario.objects.get(slug=CONVERTED)
        row.versions.all().delete()                       # the database as it was before 0008
        start = self._start(CONVERTED).json()             # an in-progress attempt from before the deploy
        importlib.import_module("practice.migrations.0008_version_origin").snapshot_existing(
            __import__("django.apps", fromlist=["apps"]).apps, None)
        self.assertEqual(row.versions.get().origin, "seed")
        old_steps = copy.deepcopy(row.content["steps"])
        decide = _publish_new_answer(Scenario.objects.get(pk=row.pk))
        attempt = Attempt.objects.get(pk=start["attempt_id"])
        self.assertEqual(attempt_content(attempt)["steps"], old_steps)
        self.assertTrue(self._answer(start["attempt_id"], decide, old_steps[decide])["correct"])

    def test_preview_attempts_award_nothing_and_record_nothing(self):
        start = self._start(CONVERTED).json()
        Attempt.objects.filter(pk=start["attempt_id"]).update(is_preview=True)
        steps = Scenario.objects.get(slug=CONVERTED).content["steps"]
        for index, step in enumerate(steps):
            if step["type"] != "story":
                self.client.post(reverse("practice:api_answer", args=[start["attempt_id"]]),
                                 json.dumps({"step": index, "answer": answer_for(step)}),
                                 content_type="application/json")
        done = self.client.post(reverse("practice:api_complete", args=[start["attempt_id"]])).json()
        self.user.refresh_from_db()
        self.assertEqual((done["xp"], done["badges"], self.user.xp), (0, [], 0))
        self.assertEqual(done["accuracy"], 100)
        self.assertFalse(PracticeSession.objects.filter(user=self.user).exists())
        self.assertEqual(Attempt.objects.get(pk=start["attempt_id"]).xp_awarded, 0)

    def _signals(self):
        """Everything leaderboards, achievements, Cyber DNA, analytics and dashboards read."""
        from accounts.models import UserActivityDay
        from achievements.models import UserBadge
        from dashboard import ops
        from notifications.models import Notification
        from practice.adaptive import get_cyber_dna
        user = User.objects.get(pk=self.user.pk)
        return {
            "user": (user.xp, user.level, user.current_streak, user.longest_streak, user.last_active_date),
            "badges": list(UserBadge.objects.values_list("user_id", "badge_id")),
            "practice": list(PracticeSession.objects.values_list("pk", flat=True)),
            "activity_days": list(UserActivityDay.objects.values_list("user_id", "day")),
            "notifications": Notification.objects.count(),
            "cyber_dna": get_cyber_dna(user),
            "leaderboard": ops.leaderboard_summary(),
            "practice_analytics": ops.practice_rows(),
            "student_practice": ops.student_practice(user),
            "completed": Attempt.objects.real().filter(finished_at__isnull=False).count(),
            "center_xp": self.client.get(reverse("practice:center")).context["practice_xp"],
        }

    def test_preview_attempts_leave_every_progress_signal_unchanged(self):
        before = self._signals()
        start = self._start(CHOICE).json()
        Attempt.objects.filter(pk=start["attempt_id"]).update(is_preview=True)
        steps = Scenario.objects.get(slug=CHOICE).content["steps"]
        branch = next(i for i, s in enumerate(steps) if s["type"] == "branch")
        for scene_no, scene in enumerate(steps[branch]["scenes"]):   # the best ending: badge-worthy if it counted
            good = next(i for i, c in enumerate(scene["choices"]) if c["effects"]["kind"] == "good")
            self.client.post(reverse("practice:api_answer", args=[start["attempt_id"]]),
                             json.dumps({"step": branch, "answer": {"scene": scene_no, "choice": good}}),
                             content_type="application/json")
        done = self.client.post(reverse("practice:api_complete", args=[start["attempt_id"]]))
        self.assertEqual(done.status_code, 200, done.content)
        self.assertEqual(self._signals(), before)

    def test_preview_runs_older_than_seven_days_are_purged(self):
        from accounts.retention import purge_preview_attempts, run_all
        old = timezone.now() - timedelta(days=8)
        rows = {}
        for name, preview, when in (("old_preview", True, old), ("new_preview", True, timezone.now()),
                                    ("old_real", False, old)):
            rows[name] = self._start(CONVERTED).json()["attempt_id"]
            Attempt.objects.filter(pk=rows[name]).update(is_preview=preview, started_at=when)
        self.assertEqual(purge_preview_attempts(dry_run=True), 1)
        self.assertEqual(run_all()["old_practice_preview_runs"], 1)
        self.assertEqual(set(Attempt.objects.values_list("pk", flat=True)), {rows["new_preview"], rows["old_real"]})
        self.assertEqual(purge_preview_attempts(), 0)


class MetaBlockTests(TestCase):
    def test_public_content_keeps_meta_and_unknown_keys_but_strips_answers(self):
        content = {
            "meta": {"badge": "Cipher Sleuth", "description": "Lock down a file share."},
            "future_key": {"anything": [1, 2]},
            "steps": [{"type": "mcq", "options": ["a", "b"], "correct": 1, "feedback": {}}],
        }
        public = public_content(content)
        self.assertEqual(public["meta"], content["meta"])
        self.assertEqual(public["future_key"], content["future_key"])
        self.assertFalse(set(public["steps"][0]) & ANSWER_KEYS)
        self.assertFalse(set(content["meta"]) & ANSWER_KEYS)   # meta never carries an answer key


class StudioGroupTests(TestCase):
    def _member(self, group, email):
        user = User.objects.create_user(email=email, password="testpass123", username=email.split("@")[0], is_staff=True)
        user.groups.add(Group.objects.get(name=group))
        return User.objects.get(pk=user.pk)   # fresh permission cache

    def test_groups_carry_the_studio_permissions(self):
        editor = self._member("Content Editor", "editor@example.com")
        publisher = self._member("Content Publisher", "publisher@example.com")
        for perm in ("practice.use_studio", "practice.add_scenario", "practice.change_scenario"):
            self.assertTrue(editor.has_perm(perm), perm)
            self.assertTrue(publisher.has_perm(perm), perm)
        self.assertFalse(editor.has_perm("practice.publish_scenario"))
        self.assertTrue(publisher.has_perm("practice.publish_scenario"))

    def test_editors_and_publishers_get_403_on_every_command_center_page(self):
        from dashboard import ops_urls
        dummy = {"int": 1, "string": "x", "slug": "x", "path": "x"}
        for group in ("Content Editor", "Content Publisher"):
            self.client.force_login(self._member(group, f"{group.split()[1].lower()}@example.com"))
            for pattern in ops_urls.urlpatterns:
                if not isinstance(pattern, URLPattern) or not pattern.name:
                    continue   # unnamed aliases redirect to a named page checked here
                kwargs = {name: dummy[type(conv).__name__.replace("Converter", "").lower()]
                          for name, conv in pattern.pattern.converters.items()}
                url = reverse(f"ops:{pattern.name}", kwargs=kwargs)
                self.assertEqual(self.client.get(url).status_code, 403, f"{group} GET {url}")
                self.assertEqual(self.client.post(url).status_code, 403, f"{group} POST {url}")
