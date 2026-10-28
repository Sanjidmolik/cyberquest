"""Practice Studio, phase 1: status, versions, preview attempts, groups, and the seed rules
that keep deploys (build.sh) from overwriting studio work."""

import copy
import json
import re
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import URLPattern, reverse

from practice.graders import ANSWER_KEYS, public_content
from practice.models import Attempt, PracticeSession, Scenario, ScenarioVersion, StudioAuditLog
from practice.seeding import content_hash
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
        self.assertIn(f"update {CONVERTED}", out)
        row.refresh_from_db()
        self.assertEqual((row.content, row.version), (old, 2))

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
        ScenarioVersion.objects.create(scenario=row, version=row.version, content=row.content)
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

    def test_an_attempt_is_graded_on_the_version_it_started_on(self):
        start = self._start(CONVERTED).json()
        row = Scenario.objects.get(slug=CONVERTED)
        old_steps = copy.deepcopy(row.content["steps"])
        # Publish v2 with a different right answer for the decision.
        ScenarioVersion.objects.create(scenario=row, version=row.version, content=copy.deepcopy(row.content))
        decide = next(i for i, s in enumerate(row.content["steps"]) if s["type"] == "mcq")
        right = old_steps[decide]["correct"]
        row.content["steps"][decide]["correct"] = (right + 1) % len(old_steps[decide]["options"])
        row.version += 1
        row.save()
        res = self.client.post(reverse("practice:api_answer", args=[start["attempt_id"]]),
                               json.dumps({"step": decide, "answer": answer_for(old_steps[decide])}),
                               content_type="application/json").json()
        self.assertTrue(res["correct"])

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
