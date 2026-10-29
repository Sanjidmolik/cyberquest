"""Practice Studio, phase 4: the Basics and Steps wizard.

Rules from the owner: XP is a fixed 50; autosave saves the draft only (no audit); optimistic
locking never overwrites another admin's work; sign-in / CSRF failures keep the typed data;
required steps stay locked; drafting is lenient (validate_content only at publish); admin text
reaches students as plain text."""

import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from courses.models import Course
from practice.graders import validate_content
from practice.models import Scenario, StudioAuditLog
from practice.seeding import canonical_json
from practice.studio import services
from practice.studio.serializers import SessionSerializer
from practice.testing import convert_all

User = get_user_model()
SCRIPT = "<script>alert(1)</script>"


def member(name, group=None, **extra):
    user = User.objects.create_user(email=f"{name}@example.com", password="testpass123", username=name, **extra)
    if group:
        user.groups.add(Group.objects.get(name=group))
    return User.objects.get(pk=user.pk)


class WizardTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        convert_all()
        cls.editor = member("ed", "Content Editor", is_staff=True)
        cls.other_editor = member("ann", "Content Editor", is_staff=True)
        cls.topic = Course.objects.get(code="MOD-01")

    def setUp(self):
        self.client.force_login(self.editor)
        self.draft = services.from_template("incident", self.topic, self.editor)

    def save(self, payload, scenario=None, client=None):
        scenario = scenario or self.draft
        return (client or self.client).post(reverse("studio:save", args=[scenario.slug]), json.dumps(payload),
                                            content_type="application/json")

    def editor_data(self, scenario=None):
        scenario = Scenario.objects.get(pk=(scenario or self.draft).pk)
        return SessionSerializer.from_json(services.working_content(scenario)), scenario.draft_revision

    def basics(self, **changes):
        data = {"title": "Payroll scam", "topic": str(self.topic.pk), "difficulty": "beginner", "est_minutes": 12,
                "badge": "", "description": ""}
        data.update(changes)
        return data


class XpTests(WizardTestCase):
    def test_every_studio_session_is_worth_50_xp(self):
        source = Scenario.objects.get(slug="phish-01-choice")
        Scenario.objects.filter(pk=source.pk).update(xp_reward=120)            # even if a source differs
        made = [self.draft, services.duplicate(Scenario.objects.get(pk=source.pk), self.editor)]
        payload = services.export_payload(source)
        payload["xp_reward"] = 999
        made.append(services.import_session(json.dumps(payload).encode(), self.editor))
        self.assertEqual([s.xp_reward for s in made], [50, 50, 50])
        page = self.client.get(reverse("studio:basics", args=[self.draft.slug]))
        self.assertContains(page, "50 XP")
        self.assertNotContains(page, 'name="xp')
        self.client.post(reverse("studio:basics", args=[self.draft.slug]),
                         {**self.basics(), "xp_reward": "500", "revision": "0"})
        self.assertEqual(Scenario.objects.get(pk=self.draft.pk).xp_reward, 50)


class SavingTests(WizardTestCase):
    def test_unchanged_editor_data_round_trips(self):
        data, revision = self.editor_data()
        before = canonical_json(self.draft.content)
        res = self.save({"revision": revision, "session": data})
        self.assertEqual(res.status_code, 200, res.content)
        row = Scenario.objects.get(pk=self.draft.pk)
        self.assertEqual(canonical_json(row.draft_content), before)
        self.assertEqual((row.draft_revision, res.json()["revision"]), (1, 1))

    def test_autosave_is_not_audited_but_a_manual_save_is(self):
        data, revision = self.editor_data()
        data["steps"][0]["data"]["intro"] = "Autosaved intro"
        self.assertEqual(self.save({"revision": revision, "session": data, "autosave": True}).status_code, 200)
        self.assertFalse(StudioAuditLog.objects.filter(action="edit").exists())
        self.assertEqual(Scenario.objects.get(pk=self.draft.pk).draft_content["steps"][0]["intro"], "Autosaved intro")
        self.save({"revision": revision + 1, "session": data})
        self.assertEqual(StudioAuditLog.objects.filter(action="edit").count(), 1)

    def test_basics_save_to_the_draft_and_badge_to_meta(self):
        res = self.client.post(reverse("studio:basics", args=[self.draft.slug]),
                               {**self.basics(title="Payroll scam", badge="Payroll Pro", description="Short"), "revision": "0",
                                "next": "steps"})
        self.assertRedirects(res, reverse("studio:steps", args=[self.draft.slug]))
        row = Scenario.objects.get(pk=self.draft.pk)
        self.assertEqual((row.title, row.draft_meta["title"]), ("Payroll scam", "Payroll scam"))   # never published
        self.assertEqual(row.draft_content["meta"], {"badge": "Payroll Pro", "description": "Short"})
        # The steps page doesn't send meta; saving steps keeps the badge.
        data, revision = self.editor_data()
        del data["meta"]
        self.save({"revision": revision, "session": data})
        self.assertEqual(Scenario.objects.get(pk=self.draft.pk).draft_content["meta"]["badge"], "Payroll Pro")

    def test_students_keep_the_published_version_until_publish(self):
        live = Scenario.objects.get(slug="phish-01-choice")
        published = canonical_json(live.content)
        data, revision = self.editor_data(live)
        data["steps"][0]["data"]["intro"] = "A new draft intro"
        self.assertEqual(self.save({"revision": revision, "session": data,
                                    "basics": self.basics(title="Renamed in draft")}, live).status_code, 200)
        live.refresh_from_db()
        self.assertEqual(canonical_json(live.content), published)
        self.assertEqual(live.title, "The urgent CEO request")                 # the published title
        self.assertEqual((live.draft_meta["title"], live.source), ("Renamed in draft", "studio"))
        student = member("student")
        self.client.force_login(student)
        start = self.client.post(reverse("practice:api_start"), json.dumps({"scenario": live.slug}),
                                 content_type="application/json").json()
        self.assertNotEqual(start["content"]["steps"][0]["intro"], "A new draft intro")


class LockingTests(WizardTestCase):
    def test_a_stale_revision_never_overwrites_and_says_who_saved(self):
        data, revision = self.editor_data()
        mine = json.loads(json.dumps(data))
        theirs = json.loads(json.dumps(data))
        theirs["steps"][0]["data"]["intro"] = "Ann's version"
        other = Client()
        other.force_login(self.other_editor)
        self.assertEqual(self.save({"revision": revision, "session": theirs}, client=other).status_code, 200)
        mine["steps"][0]["data"]["intro"] = "My version"
        res = self.save({"revision": revision, "session": mine})
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["by"], "ann")
        self.assertIn("ann changed this session", res.json()["error"])
        self.assertEqual(Scenario.objects.get(pk=self.draft.pk).draft_content["steps"][0]["intro"], "Ann's version")
        basics_page = self.client.post(reverse("studio:basics", args=[self.draft.slug]),
                                       {**self.basics(title="Mine"), "revision": str(revision)})
        self.assertContains(basics_page, "ann changed this session")
        self.assertNotEqual(Scenario.objects.get(pk=self.draft.pk).title, "Mine")

    def test_expired_sign_in_and_csrf_failures_dont_lose_data(self):
        data, revision = self.editor_data()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.editor)
        refused = self.save({"revision": revision, "session": data}, client=client)
        self.assertEqual(refused.status_code, 403)
        self.assertNotIn("application/json", refused["Content-Type"])           # the page sees "not JSON"
        signed_out = self.save({"revision": revision, "session": data}, client=Client())
        self.assertEqual(signed_out.status_code, 302)
        self.assertEqual(Scenario.objects.get(pk=self.draft.pk).draft_revision, 0)
        script = (Path(settings.BASE_DIR) / "practice/static/practice/studio/studio-editor.js").read_text(encoding="utf-8")
        for needle in ("res.redirected", "application/json", "signed out", "still here", "beforeunload",
                       "AUTOSAVE_MS = 30000", "409"):
            self.assertIn(needle, script)
        self.assertNotIn("location.reload()", script.split("function showAlert")[0])  # never reloads by itself


class LenientDraftTests(WizardTestCase):
    def test_incomplete_drafts_save_and_only_publish_checks_them(self):
        data, revision = self.editor_data()
        steps = data["steps"]
        steps[1]["data"]["alerts"] = []                                          # triage with no alerts
        steps[1]["data"]["severity"] = None
        mcq = next(s for s in steps if s["type"] == "mcq")
        for option in mcq["data"]["options"]:
            option["correct"] = False                                            # no right answer yet
            option["text"] = ""
        steps.insert(1, steps.pop(3))                                             # out of recipe order
        res = self.save({"revision": revision, "session": data})
        self.assertEqual(res.status_code, 200, res.content)
        draft = Scenario.objects.get(pk=self.draft.pk).draft_content
        with self.assertRaises(Exception):
            validate_content("incident", draft)

    def test_add_reorder_and_remove_optional_steps(self):
        data, revision = self.editor_data()
        config = self.client.get(reverse("studio:steps", args=[self.draft.slug])).context["editor_config"]
        data["steps"].append({"uid": None, "type": "mcq", "data": config["blanks"]["mcq"]})
        data["steps"][1], data["steps"][2] = data["steps"][2], data["steps"][1]
        removed = data["steps"].pop(next(i for i, s in enumerate(data["steps"]) if s["type"] == "order"))
        self.assertEqual(self.save({"revision": revision, "session": data}).status_code, 200)
        types = [s["type"] for s in Scenario.objects.get(pk=self.draft.pk).draft_content["steps"]]
        self.assertEqual(types, ["story", "hotspot", "triage", "mcq", "mcq"])
        self.assertEqual(removed["type"], "order")


class StructureTests(WizardTestCase):
    def _rejected(self, mutate, scenario=None, status=400):
        data, revision = self.editor_data(scenario)
        mutate(data)
        res = self.save({"revision": revision, "session": data}, scenario)
        self.assertEqual(res.status_code, status, res.content)
        self.assertEqual(Scenario.objects.get(pk=(scenario or self.draft).pk).draft_revision, revision)
        return res.json()["error"]

    def test_required_steps_stay_locked(self):
        self.assertIn("briefing", self._rejected(lambda d: d["steps"].pop(0)))
        self.assertIn("briefing", self._rejected(lambda d: d["steps"].insert(1, d["steps"].pop(0))))
        choice = services.from_template("choice", self.topic, self.editor)
        self.assertIn("choices", self._rejected(lambda d: d["steps"].pop(1), choice).lower())
        self.assertIn("choices", self._rejected(lambda d: d["steps"].append(dict(d["steps"][1], uid=None)), choice).lower())

    def test_wrong_kinds_damaged_data_and_oversized_text_are_refused(self):
        self.assertIn("can't have", self._rejected(lambda d: d["steps"].append({"uid": None, "type": "branch", "data": {}})))
        self._rejected(lambda d: d["steps"][1].update(uid=0))                    # uid of a different step type
        self._rejected(lambda d: d["steps"][1].update(data="nope"))
        self._rejected(lambda d: d["steps"][0]["data"].update(intro="x" * 4001))
        self._rejected(lambda d: d["steps"][1]["data"].update(alerts=[{"from": "x"}] * 61))
        self.assertEqual(self.client.post(reverse("studio:save", args=[self.draft.slug]), b"{not json",
                                          content_type="application/json").status_code, 400)
        big = json.dumps({"revision": 0, "session": {"steps": [], "pad": "x" * 300_000}})
        self.assertEqual(self.client.post(reverse("studio:save", args=[self.draft.slug]), big,
                                          content_type="application/json").status_code, 413)


class AccessTests(WizardTestCase):
    def test_only_studio_editors_reach_the_wizard(self):
        urls = [reverse(name, args=[self.draft.slug]) for name in ("studio:basics", "studio:steps", "studio:save")]
        for user in (member("student"), member("staffer", is_staff=True), member("mod", "Moderator", is_staff=True)):
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403, (user.username, url))
                self.assertEqual(self.client.post(url).status_code, 403, (user.username, url))
        for user in (self.editor, member("pub", "Content Publisher", is_staff=True)):
            self.client.force_login(user)
            self.assertEqual(self.client.get(urls[0]).status_code, 200)
            self.assertEqual(self.client.get(urls[1]).status_code, 200)

    def test_new_sessions_open_in_the_wizard(self):
        res = self.client.post(reverse("studio:template", args=["choice"]), {"topic": self.topic.pk})
        self.assertTrue(res.url.endswith("/basics/"))
        self.assertContains(self.client.get(res.url), "Steps")


class EscapingTests(WizardTestCase):
    def test_admin_typed_text_reaches_students_as_plain_text(self):
        live = Scenario.objects.get(slug="phish-01-choice")
        content = json.loads(json.dumps(live.content))
        content["steps"][0]["intro"] = SCRIPT
        content["steps"][0]["desc"] = SCRIPT
        Scenario.objects.filter(pk=live.pk).update(title=SCRIPT, content=content)
        self.client.force_login(member("student"))
        page = self.client.get(reverse("practice:session", args=[live.slug])).content.decode()
        self.assertNotIn(SCRIPT, page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        center = self.client.get(reverse("practice:center")).content.decode()
        self.assertNotIn(SCRIPT, center)
        # The player builds elements with text nodes only: no way to inject HTML from content.
        js = Path(settings.BASE_DIR) / "practice/static/practice/js"
        engine = (js / "engine.js").read_text(encoding="utf-8")
        self.assertNotIn('k === "html"', engine)
        for script in [js / "engine.js", *sorted((js / "steps").glob("*.js"))]:
            text = script.read_text(encoding="utf-8")
            self.assertNotIn("html:", text, script.name)
            self.assertNotIn("insertAdjacentHTML", text, script.name)

    def test_studio_pages_escape_admin_text_too(self):
        Scenario.objects.filter(pk=self.draft.pk).update(title=SCRIPT)
        for name in ("studio:basics", "studio:steps"):
            page = self.client.get(reverse(name, args=[self.draft.slug])).content.decode()
            self.assertNotIn(SCRIPT, page)
        editor_js = (Path(settings.BASE_DIR) / "practice/static/practice/studio/studio-editor.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", editor_js)
