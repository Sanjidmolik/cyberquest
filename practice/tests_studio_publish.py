"""Practice Studio, phase 6: check and publish.

The checklist names every rule with a Fix link; publish needs every check, the draft revision
and the publish permission (checked on the server); students mid-session keep their version;
archive hides without deleting; restore only makes a draft; every action is audited."""

import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from courses.models import Course
from notifications.models import Notification
from practice.models import Attempt, PracticeSession, Scenario, ScenarioVersion, StudioAuditLog
from practice.studio import checks, publishing, services
from practice.studio.checks import EXAMPLE_MIN_LENGTH
from practice.testing import answer_for, convert_all, play_through

User = get_user_model()
SEED = "phish-01-choice"
GRADED_SEED = "phishing-bec-payment"            # no branch step: answered step by step below


def member(name, group=None, **extra):
    user = User.objects.create_user(email=f"{name}@example.com", password="testpass123", username=name, **extra)
    if group:
        user.groups.add(Group.objects.get(name=group))
    return User.objects.get(pk=user.pk)


def rewrite(value, counter=None):
    """The same content with every long text replaced, so no template example is left."""
    counter = counter if counter is not None else [0]
    if isinstance(value, str) and len(value.strip()) >= EXAMPLE_MIN_LENGTH:
        counter[0] += 1
        return f"Our own wording for this part, number {counter[0]}"
    if isinstance(value, dict):
        return {k: rewrite(v, counter) for k, v in value.items()}
    if isinstance(value, list):
        return [rewrite(v, counter) for v in value]
    return value


def failed(scenario):
    return [rule for rule in checks.run(Scenario.objects.get(pk=scenario.pk)) if not rule["ok"]]


class PublishTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        convert_all()
        cls.editor = member("ed", "Content Editor", is_staff=True)
        cls.publisher = member("pub", "Content Publisher", is_staff=True)
        cls.topic = Course.objects.get(code="MOD-01")

    def setUp(self):
        self.client.force_login(self.publisher)

    def as_user(self, user):
        client = Client()
        client.force_login(user)
        return client

    def ready_draft(self):
        """A never-published draft from the incident template, with its example text rewritten."""
        draft = services.from_template("incident", self.topic, self.editor)
        draft.draft_content = rewrite(draft.content)
        draft.draft_meta = {"title": "Our incident drill", "difficulty": "beginner", "est_minutes": 12, "topic": self.topic.pk}
        draft.save()
        self.assertEqual(failed(draft), [])
        return Scenario.objects.get(pk=draft.pk)

    def edit_live(self, slug=SEED, intro="A brand new briefing for students"):
        row = Scenario.objects.get(slug=slug)
        content = json.loads(json.dumps(row.content))
        content["steps"][0]["intro"] = intro
        row.draft_content = content
        row.draft_meta = {"title": "Renamed session", "difficulty": row.difficulty, "est_minutes": row.est_minutes,
                          "topic": row.topic_id}
        row.save()
        return row

    def post(self, name, scenario, client=None, **data):
        args = [scenario.slug] + ([data.pop("version")] if "version" in data else [])
        return (client or self.client).post(reverse(f"studio:{name}", args=args), data)

    def start(self, client, slug=SEED):
        res = client.post(reverse("practice:api_start"), json.dumps({"scenario": slug}), content_type="application/json")
        self.assertEqual(res.status_code, 201, res.content)
        return res.json()


class ChecklistTests(PublishTestCase):
    def test_every_seed_session_passes_and_a_fresh_template_flags_its_example_text(self):
        for row in Scenario.objects.all():
            self.assertEqual(failed(row), [], row.slug)
        draft = services.from_template("simulation", self.topic, self.editor)
        self.assertEqual([r["text"] for r in failed(draft)], ["No example text from a template is left unchanged."])

    def test_each_failure_is_plain_english_with_a_fix_link_to_the_step_and_field(self):
        draft = self.ready_draft()
        content = draft.draft_content
        mcq = next(i for i, s in enumerate(content["steps"]) if s["type"] == "mcq")
        content["steps"][mcq]["tips"]["start"] = ""              # the question is what Hana asks
        content["debrief"]["sub"] = ""
        draft.draft_meta["title"] = ""
        draft.save()
        rules = {r["text"]: r["fix"] for r in failed(draft)}
        steps_url = reverse("studio:steps", args=[draft.slug])
        self.assertEqual(rules["The session has a title."], reverse("studio:basics", args=[draft.slug]) + "#b-title")
        self.assertEqual(rules[f"Step {mcq + 1} · Question: Question (Hana asks it) is empty."],
                         f"{steps_url}#step-{mcq + 1}:question")
        self.assertEqual(rules["The results screen has a one-line summary."], f"{steps_url}#results:sub")

        page = self.as_user(self.editor).get(reverse("studio:check", args=[draft.slug]))
        self.assertContains(page, "checks to fix before this can be published")
        self.assertContains(page, f'href="{steps_url}#step-{mcq + 1}:question">Fix</a>', html=False)
        self.assertContains(page, "Passed:")

    def test_answers_and_order_are_checked(self):
        draft = self.ready_draft()
        steps = draft.draft_content["steps"]
        steps[1], steps[2] = steps[2], steps[1]                      # hotspot before triage
        mcq = next(s for s in steps if s["type"] == "mcq")
        mcq["correct"] = 99
        draft.save()
        texts = [r["text"] for r in failed(draft)]
        self.assertIn("The steps follow the incident order (Briefing → Triage → Find the clues → Question → "
                      "Put in order).", texts)
        self.assertTrue(any("Tick the right answer." in t for t in texts), texts)
        self.assertTrue(any(t.startswith("The player's own content check fails") for t in texts), texts)


class PermissionTests(PublishTestCase):
    def test_editors_cannot_publish_archive_unarchive_or_restore_by_direct_post(self):
        draft = self.ready_draft()
        live = self.edit_live()
        editor = self.as_user(self.editor)
        for name, scenario, data in (("publish", draft, {"revision": draft.draft_revision}),
                                     ("publish", live, {"revision": live.draft_revision}),
                                     ("archive", live, {}), ("unarchive", live, {}),
                                     ("restore", live, {"version": 1, "revision": live.draft_revision})):
            self.assertEqual(self.post(name, scenario, editor, **data).status_code, 403, name)
        for user in (member("student"), member("staffer", is_staff=True), member("mod", "Moderator", is_staff=True)):
            self.assertEqual(self.post("publish", draft, self.as_user(user), revision=0).status_code, 403)
        self.assertEqual(Scenario.objects.get(pk=draft.pk).status, Scenario.DRAFT)
        self.assertEqual(Scenario.objects.get(pk=live.pk).status, Scenario.PUBLISHED)
        self.assertEqual(Scenario.objects.get(pk=live.pk).version, 1)
        self.assertFalse(StudioAuditLog.objects.filter(action__in=["publish", "archive", "unarchive", "restore"]).exists())

    def test_get_is_not_allowed_on_actions(self):
        live = Scenario.objects.get(slug=SEED)
        for name in ("publish", "archive", "unarchive", "review"):
            self.assertEqual(self.client.get(reverse(f"studio:{name}", args=[live.slug])).status_code, 405)

    def test_editors_see_request_review_and_publishers_see_publish(self):
        draft = self.ready_draft()
        url = reverse("studio:check", args=[draft.slug])
        as_editor = self.as_user(self.editor).get(url)
        self.assertContains(as_editor, "Request review")
        self.assertNotContains(as_editor, "Publish now")
        self.assertNotContains(as_editor, reverse("studio:archive", args=[draft.slug]))
        as_publisher = self.client.get(url)
        self.assertContains(as_publisher, "Students will see this version immediately.")
        self.assertNotContains(as_publisher, "Request review")
        self.assertEqual(self.as_user(member("mod", "Moderator", is_staff=True)).get(url).status_code, 403)

    def test_request_review_notifies_publishers_and_superusers_only(self):
        draft = self.ready_draft()
        boss = member("boss", is_staff=True, is_superuser=True)
        mod = member("mod", "Moderator", is_staff=True)
        retired = member("old", "Content Publisher", is_staff=True, is_active=False)
        res = self.post("review", draft, self.as_user(self.editor))
        self.assertRedirects(res, reverse("studio:check", args=[draft.slug]))
        notified = set(Notification.objects.values_list("user__username", flat=True))
        self.assertEqual(notified, {self.publisher.username, boss.username})
        self.assertNotIn(mod.username, notified)
        self.assertNotIn(retired.username, notified)
        note = Notification.objects.get(user=self.publisher)
        self.assertIn("Our incident drill", note.message)
        self.assertEqual(note.link_url, reverse("studio:check", args=[draft.slug]))
        self.assertTrue(StudioAuditLog.objects.filter(action="review", scenario=draft, user=self.editor).exists())
        self.post("review", draft, self.as_user(self.editor))                    # within the cooldown: no repeat
        self.assertEqual(Notification.objects.count(), 2)


class PublishFlowTests(PublishTestCase):
    def test_publish_is_blocked_while_a_check_fails(self):
        draft = services.from_template("incident", self.topic, self.editor)  # example text still in it
        page = self.client.get(reverse("studio:check", args=[draft.slug]))
        self.assertContains(page, 'disabled aria-describedby="st-publish-why"')
        res = self.post("publish", draft, revision=draft.draft_revision)
        self.assertRedirects(res, reverse("studio:check", args=[draft.slug]))
        draft.refresh_from_db()
        self.assertEqual(draft.status, Scenario.DRAFT)
        self.assertFalse(draft.versions.exists())
        self.assertFalse(StudioAuditLog.objects.filter(action="publish").exists())
        with self.assertRaises(publishing.ChecksFailed):
            publishing.publish(draft.pk, self.publisher, revision=draft.draft_revision)

    def test_first_publish_snapshots_audits_and_shows_students(self):
        draft = self.ready_draft()
        student = self.as_user(member("student"))
        self.assertEqual(student.post(reverse("practice:api_start"), json.dumps({"scenario": draft.slug}),
                                      content_type="application/json").status_code, 404)
        res = self.post("publish", draft, revision=draft.draft_revision)
        self.assertRedirects(res, reverse("studio:check", args=[draft.slug]))
        row = Scenario.objects.get(pk=draft.pk)
        self.assertEqual((row.status, row.version, row.title, row.est_minutes, row.xp_reward),
                         (Scenario.PUBLISHED, 1, "Our incident drill", 12, 50))
        self.assertIsNone(row.draft_content)
        snapshot = row.versions.get()
        self.assertEqual((snapshot.version, snapshot.origin, snapshot.published_by), (1, ScenarioVersion.STUDIO, self.publisher))
        self.assertEqual(snapshot.content, row.content)
        self.assertEqual(snapshot.meta["changes"], ["First published version"])
        self.assertTrue(StudioAuditLog.objects.filter(action="publish", scenario=row, user=self.publisher, version=1).exists())
        self.assertEqual(self.start(student, row.slug)["content"]["steps"][0]["intro"], row.content["steps"][0]["intro"])

    def test_publish_uses_the_draft_revision_check(self):
        live = self.edit_live()
        stale = live.draft_revision - 1
        res = self.post("publish", live, revision=stale)
        self.assertRedirects(res, reverse("studio:check", args=[live.slug]))
        live.refresh_from_db()
        self.assertEqual((live.version, live.title), (1, Scenario.objects.get(slug=SEED).title))
        self.assertIsNotNone(live.draft_content)
        self.assertFalse(StudioAuditLog.objects.filter(action="publish").exists())

    def test_republish_makes_a_new_version_with_a_what_changed_summary(self):
        live = self.edit_live()
        old_title = live.title
        self.post("publish", live, revision=live.draft_revision)
        live.refresh_from_db()
        self.assertEqual((live.version, live.title, live.source), (2, "Renamed session", Scenario.STUDIO))
        v2 = live.versions.get(version=2)
        self.assertEqual(v2.meta["changes"], [f"Title: “{old_title}” → “Renamed session”", "Edited 1 step"])
        self.assertEqual(live.versions.get(version=1).origin, ScenarioVersion.SEED)       # the old live version kept
        # Nothing new to publish now.
        self.post("publish", live, revision=live.draft_revision)
        self.assertEqual(Scenario.objects.get(pk=live.pk).version, 2)

        versions = self.as_user(self.editor).get(reverse("studio:versions", args=[live.slug]))
        self.assertContains(versions, "v2")
        self.assertContains(versions, "Edited 1 step")
        self.assertContains(versions, self.publisher.username)
        self.assertContains(versions, "Seed command")
        self.assertNotContains(versions, "Restore as draft")                         # editors can't restore
        self.assertContains(self.client.get(reverse("studio:versions", args=[live.slug])), "Restore as draft")

    def test_what_changed_lists_added_and_removed_steps(self):
        old = {"steps": [{"type": "story"}, {"type": "triage"}, {"type": "mcq"}], "debrief": {"sub": "a"}}
        new = {"steps": [{"type": "story"}, {"type": "triage", "title": "x"}, {"type": "order"}], "debrief": {"sub": "b"}}
        self.assertEqual(publishing.what_changed(old, {"title": "A"}, new, {"title": "A"}),
                         ["Added 1 step: Put in order", "Removed 1 step: Question", "Edited 1 step",
                          "Edited the results screen"])

    def test_students_mid_session_keep_their_original_version(self):
        student = self.as_user(member("student"))
        started = self.start(student, GRADED_SEED)
        attempt = Attempt.objects.get(pk=started["attempt_id"])
        v1 = Scenario.objects.get(slug=GRADED_SEED).content
        live = self.edit_live(GRADED_SEED, intro="Version two briefing")
        self.post("publish", live, revision=live.draft_revision)
        self.assertEqual(Scenario.objects.get(slug=GRADED_SEED).version, 2)
        self.assertEqual(attempt.state["version"], 1)
        for index, step in enumerate(v1["steps"]):
            if step["type"] in ("story",):
                continue
            res = student.post(reverse("practice:api_answer", args=[attempt.pk]),
                               json.dumps({"step": index, "answer": answer_for(step)}), content_type="application/json")
            self.assertEqual(res.status_code, 200, res.content)
        done = student.post(reverse("practice:api_complete", args=[attempt.pk])).json()
        self.assertEqual(done["accuracy"], 100)
        fresh = self.start(self.as_user(member("late")), GRADED_SEED)
        self.assertEqual(fresh["content"]["steps"][0]["intro"], "Version two briefing")


class RestoreTests(PublishTestCase):
    def test_restore_makes_a_draft_and_students_still_see_the_live_version(self):
        live = self.edit_live(intro="Version two briefing")
        self.post("publish", live, revision=live.draft_revision)
        live.refresh_from_db()
        res = self.post("restore", live, version=1, revision=live.draft_revision)
        self.assertRedirects(res, reverse("studio:check", args=[live.slug]))
        row = Scenario.objects.get(pk=live.pk)
        self.assertEqual((row.status, row.version), (Scenario.PUBLISHED, 2))
        self.assertEqual(row.draft_content, row.versions.get(version=1).content)
        self.assertEqual(row.draft_meta["title"], row.versions.get(version=1).meta["title"])
        self.assertEqual(row.content["steps"][0]["intro"], "Version two briefing")
        self.assertEqual(row.versions.count(), 2)
        student = self.as_user(member("student"))
        self.assertEqual(self.start(student)["content"]["steps"][0]["intro"], "Version two briefing")
        audit = StudioAuditLog.objects.get(action="restore")
        self.assertEqual((audit.user, audit.version), (self.publisher, 2))
        self.assertIn("Restored v1 as a draft", audit.summary)
        # A publisher then checks and publishes it as version 3.
        self.post("publish", row, revision=row.draft_revision)
        row.refresh_from_db()
        self.assertEqual(row.version, 3)
        self.assertEqual(row.content, row.versions.get(version=1).content)

    def test_restore_checks_the_revision_and_the_version(self):
        live = self.edit_live()
        self.post("restore", live, version=1, revision=live.draft_revision - 1)
        self.post("restore", live, version=42, revision=live.draft_revision)
        self.assertEqual(Scenario.objects.get(pk=live.pk).draft_content, live.draft_content)
        self.assertFalse(StudioAuditLog.objects.filter(action="restore").exists())


class ArchiveTests(PublishTestCase):
    def test_archive_hides_from_students_but_keeps_history_and_xp(self):
        student_user = member("student")
        student = self.as_user(student_user)
        play_through(student, SEED)
        attempts = Attempt.objects.filter(user=student_user).count()
        student_user.refresh_from_db()
        xp, sessions = student_user.xp, PracticeSession.objects.filter(user=student_user).count()
        self.assertGreater(xp, 0)
        session_url = reverse("practice:session", args=[SEED])
        self.assertContains(student.get(reverse("practice:center")), session_url)

        live = Scenario.objects.get(slug=SEED)
        res = self.post("archive", live)
        self.assertRedirects(res, reverse("studio:check", args=[SEED]))
        self.assertEqual(Scenario.objects.get(slug=SEED).status, Scenario.ARCHIVED)
        self.assertNotContains(student.get(reverse("practice:center")), session_url)
        self.assertEqual(student.get(session_url).status_code, 404)
        self.assertEqual(student.post(reverse("practice:api_start"), json.dumps({"scenario": SEED}),
                                      content_type="application/json").status_code, 404)
        student_user.refresh_from_db()
        self.assertEqual(student_user.xp, xp)
        self.assertEqual(PracticeSession.objects.filter(user=student_user).count(), sessions)
        self.assertEqual(Attempt.objects.filter(user=student_user).count(), attempts)
        self.assertContains(student.get(reverse("practice:history")), live.title)

        self.post("unarchive", live)
        self.assertEqual(Scenario.objects.get(slug=SEED).status, Scenario.PUBLISHED)
        self.assertContains(student.get(reverse("practice:center")), session_url)
        actions = list(StudioAuditLog.objects.filter(scenario=live).values_list("action", flat=True))
        self.assertEqual(sorted(actions), ["archive", "unarchive"])

    def test_a_never_published_draft_unarchives_as_a_draft(self):
        draft = self.ready_draft()
        self.post("archive", draft)
        self.assertEqual(Scenario.objects.get(pk=draft.pk).status, Scenario.ARCHIVED)
        self.post("unarchive", draft)
        self.assertEqual(Scenario.objects.get(pk=draft.pk).status, Scenario.DRAFT)
        self.assertEqual(StudioAuditLog.objects.filter(scenario=draft, action__in=["archive", "unarchive"]).count(), 2)

    def test_publishing_an_archived_session_with_a_draft_brings_it_back(self):
        live = self.edit_live()
        self.post("archive", live)
        live.refresh_from_db()
        self.post("publish", live, revision=live.draft_revision)
        live.refresh_from_db()
        self.assertEqual((live.status, live.version), (Scenario.PUBLISHED, 2))
