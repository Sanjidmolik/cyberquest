"""Practice Studio, phase 3: access, the Command Center nav, the session list and the start
screen (duplicate, template, import)."""

import copy
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import URLPattern, reverse

from courses.models import Course
from practice.graders import validate_content
from practice.models import Scenario, StudioAuditLog
from practice.seeding import canonical_json
from practice.studio import urls as studio_urls
from practice.studio.services import export_payload, session_content
from practice.studio.starter_templates import KINDS, load_template
from practice.testing import convert_all

User = get_user_model()


def _studio_urls():
    dummy = {"int": 1, "string": "x", "slug": "simulation", "path": "x"}
    for pattern in studio_urls.urlpatterns:
        if isinstance(pattern, URLPattern):
            kwargs = {name: dummy[type(conv).__name__.replace("Converter", "").lower()]
                      for name, conv in pattern.pattern.converters.items()}
            yield reverse(f"studio:{pattern.name}", kwargs=kwargs)


class StudioTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        convert_all()
        cls.editor = cls._member("Content Editor", "editor@example.com")
        cls.publisher = cls._member("Content Publisher", "publisher@example.com")
        cls.superuser = User.objects.create_superuser(email="root@example.com", password="testpass123", username="root")
        cls.student = User.objects.create_user(email="student@example.com", password="testpass123", username="student")
        cls.staff = User.objects.create_user(email="staff@example.com", password="testpass123", username="staff",
                                             is_staff=True)

    @classmethod
    def _member(cls, group, email):
        user = User.objects.create_user(email=email, password="testpass123", username=email.split("@")[0], is_staff=True)
        user.groups.add(Group.objects.get(name=group))
        return user


class AccessTests(StudioTestCase):
    def test_students_and_staff_without_a_studio_group_get_403_everywhere(self):
        for user in (self.student, self.staff):
            self.client.force_login(user)
            for url in _studio_urls():
                self.assertEqual(self.client.get(url).status_code, 403, f"{user.email} GET {url}")
                self.assertEqual(self.client.post(url).status_code, 403, f"{user.email} POST {url}")

    def test_signed_out_visitors_are_sent_to_the_admin_sign_in(self):
        for url in _studio_urls():
            res = self.client.get(url)
            self.assertEqual(res.status_code, 302, url)
            self.assertTrue(res.url.startswith("/admin-login/"), url)

    def test_editors_publishers_and_superusers_open_the_studio(self):
        for user in (self.editor, self.publisher, self.superuser):
            self.client.force_login(user)
            for name in ("studio:list", "studio:start", "studio:duplicate", "studio:import"):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200, f"{user.email} {name}")

    def test_every_post_needs_a_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.editor)
        topic = Course.objects.get(code="MOD-01")
        for url, data in ((reverse("studio:duplicate"), {"source": "phish-01-choice"}),
                          (reverse("studio:template", args=["choice"]), {"topic": topic.pk})):
            self.assertEqual(client.post(url, data).status_code, 403, url)
        self.assertFalse(Scenario.objects.filter(status=Scenario.DRAFT).exists())

    def test_editors_sign_in_to_the_studio_but_not_the_command_center(self):
        self.editor.set_password("testpass123")
        self.editor.save()
        login = self.client.post(reverse("admin_login"), {"email": "editor@example.com", "password": "testpass123"})
        self.assertRedirects(login, reverse("studio:list"))
        self.client.logout()
        login = self.client.post(f"{reverse('admin_login')}?next={reverse('ops:students')}",
                                 {"email": "editor@example.com", "password": "testpass123"})
        self.assertEqual(login.status_code, 200)                     # refused: not for the Command Center
        self.assertNotIn("_auth_user_id", self.client.session)


class NavTests(StudioTestCase):
    OPS_PAGES = ("ops:overview", "ops:students", "ops:courses", "ops:practice", "ops:questions",
                 "ops:certificates", "ops:settings", "ops:contact", "ops:search")

    def test_editors_and_publishers_see_only_the_studio(self):
        for user in (self.editor, self.publisher):
            self.client.force_login(user)
            page = self.client.get(reverse("studio:list")).content.decode()
            self.assertIn(f'href="{reverse("studio:list")}"', page)
            for name in self.OPS_PAGES:
                self.assertNotIn(f'href="{reverse(name)}"', page, f"{user.email} sees {name}")
                self.assertNotIn(f'action="{reverse(name)}"', page)
            self.assertNotIn(f'href="{reverse("admin:index")}"', page)

    def test_superusers_see_the_whole_command_center_and_the_studio(self):
        self.client.force_login(self.superuser)
        for page_name in ("ops:overview", "studio:list"):
            page = self.client.get(reverse(page_name)).content.decode()
            self.assertIn(f'href="{reverse("studio:list")}"', page)
            for name in self.OPS_PAGES[:-1]:
                self.assertIn(f'href="{reverse(name)}"', page, f"{page_name} misses {name}")


class ListTests(StudioTestCase):
    def setUp(self):
        self.client.force_login(self.editor)

    def test_lists_every_session_with_filters_and_search(self):
        page = self.client.get(reverse("studio:list"))
        self.assertEqual(len(page.context["rows"]), Scenario.objects.count())
        self.assertContains(page, "New practice session")
        crypto = Course.objects.get(code="MOD-04")
        rows = self.client.get(reverse("studio:list"), {"topic": crypto.pk, "kind": "simulation"}).context["rows"]
        self.assertTrue(rows)
        self.assertTrue(all(r.topic_id == crypto.pk and r.kind == "simulation" for r in rows))
        rows = self.client.get(reverse("studio:list"), {"q": "urgent CEO"}).context["rows"]
        self.assertEqual([r.slug for r in rows], ["phish-01-choice"])
        Scenario.objects.filter(slug="phish-01-choice").update(status=Scenario.DRAFT)
        rows = self.client.get(reverse("studio:list"), {"status": "draft"}).context["rows"]
        self.assertEqual([r.slug for r in rows], ["phish-01-choice"])

    def test_no_match_and_empty_states(self):
        self.assertContains(self.client.get(reverse("studio:list"), {"q": "zzz-nothing"}), "No sessions match")
        Scenario.objects.all().delete()
        self.assertContains(self.client.get(reverse("studio:list")), "No practice sessions yet")


class StartScreenTests(StudioTestCase):
    def setUp(self):
        self.client.force_login(self.editor)

    def test_four_starting_points_with_the_topic_kit_coming_soon(self):
        page = self.client.get(reverse("studio:start"))
        self.assertContains(page, "Duplicate an existing session")
        self.assertContains(page, "Recommended")
        self.assertContains(page, "Start from a template")
        self.assertContains(page, "Import a file")
        self.assertContains(page, "Generate from Topic Kit")
        self.assertContains(page, 'aria-disabled="true"')
        self.assertContains(page, "Coming soon")
        for kind in KINDS:
            self.assertContains(page, f'action="{reverse("studio:template", args=[kind])}"')

    def test_duplicating_every_session_gives_a_valid_draft_with_identical_content(self):
        for source in list(Scenario.objects.all()):
            before = canonical_json(source.content)
            res = self.client.post(reverse("studio:duplicate"), {"source": source.slug})
            self.assertEqual(res.status_code, 302, source.slug)
            copy_row = Scenario.objects.get(slug=res.url.split("created=")[1])
            self.assertNotEqual(copy_row.slug, source.slug)
            self.assertEqual((copy_row.status, copy_row.source, copy_row.version), ("draft", "studio", 1))
            self.assertEqual((copy_row.topic_id, copy_row.kind, copy_row.difficulty, copy_row.xp_reward),
                             (source.topic_id, source.kind, source.difficulty, source.xp_reward))
            self.assertIsNone(copy_row.time_limit_sec)
            # Identical except the seed's provenance, which belongs to the original only.
            self.assertEqual(canonical_json(copy_row.content), canonical_json(session_content(source.content)))
            self.assertNotIn("source", copy_row.content)
            validate_content(copy_row.kind, copy_row.content)
            self.assertEqual(canonical_json(Scenario.objects.get(pk=source.pk).content), before)
            log = StudioAuditLog.objects.get(scenario=copy_row)
            self.assertEqual((log.action, log.user), ("duplicate", self.editor))
            # A draft never reaches students.
            self.assertEqual(self.client.get(reverse("practice:session", args=[copy_row.slug])).status_code, 404)

    def test_duplicate_copies_an_unpublished_draft_when_there_is_one(self):
        source = Scenario.objects.get(slug="phish-01-choice")
        source.draft_content = {**copy.deepcopy(source.content), "debrief": {"sub": "Draft text", "learned": []}}
        source.save()
        res = self.client.post(reverse("studio:duplicate"), {"source": source.slug})
        self.assertEqual(Scenario.objects.get(slug=res.url.split("created=")[1]).content["debrief"]["sub"], "Draft text")

    def test_each_template_creates_a_draft_in_the_chosen_topic(self):
        topic = Course.objects.get(code="CQ-PRIVACY")
        for kind in KINDS:
            res = self.client.post(reverse("studio:template", args=[kind]), {"topic": topic.pk})
            row = Scenario.objects.get(slug=res.url.split("created=")[1])
            self.assertEqual((row.kind, row.topic, row.status, row.source), (kind, topic, "draft", "studio"))
            self.assertEqual(canonical_json(row.content), canonical_json(load_template(kind)["content"]))
            validate_content(kind, row.content)
        self.assertEqual(StudioAuditLog.objects.filter(action="create").count(), 3)

    def test_template_needs_a_topic_and_a_known_kind(self):
        self.client.post(reverse("studio:template", args=["choice"]), {})
        self.client.post(reverse("studio:template", args=["quiz"]), {"topic": Course.objects.first().pk})
        self.assertFalse(Scenario.objects.filter(status=Scenario.DRAFT).exists())

    def test_publishers_and_superusers_can_create_too(self):
        for user in (self.publisher, self.superuser):
            self.client.force_login(user)
            res = self.client.post(reverse("studio:duplicate"), {"source": "phish-01-choice"})
            self.assertEqual(res.status_code, 302)


class ImportTests(StudioTestCase):
    def setUp(self):
        self.client.force_login(self.editor)

    def _upload(self, payload, name="session.json", **extra):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        return self.client.post(reverse("studio:import"), {"file": SimpleUploadedFile(name, raw), **extra})

    def test_an_exported_session_imports_as_a_draft(self):
        source = Scenario.objects.get(slug="crypto-message-audit")
        res = self._upload(export_payload(source))
        self.assertEqual(res.status_code, 302)
        row = Scenario.objects.get(slug=res.url.split("created=")[1])
        self.assertNotEqual(row.slug, source.slug)                      # never overwrites
        self.assertEqual((row.status, row.source, row.topic, row.kind), ("draft", "studio", source.topic, source.kind))
        self.assertEqual(canonical_json(row.content), canonical_json(session_content(source.content)))
        self.assertIn("Imported from session.json (was crypto-message-audit)",
                      StudioAuditLog.objects.get(scenario=row).summary)

    def test_a_template_file_imports_with_a_chosen_topic(self):
        template = load_template("incident")
        topic = Course.objects.get(code="CQ-RESPONSE")
        res = self._upload(template, "incident.json", topic=topic.pk)
        self.assertEqual(Scenario.objects.get(slug=res.url.split("created=")[1]).topic, topic)

    def test_bad_files_are_refused_with_reasons_and_nothing_is_saved(self):
        good = export_payload(Scenario.objects.get(slug="phish-01-choice"))
        broken_answer = copy.deepcopy(good)
        broken_answer["content"]["steps"][1]["endings"].pop("best")
        cases = [
            (b"{not json", "not valid JSON"),
            (b"[1, 2]", "one practice session"),
            ({**good, "format": "something-else"}, "not a CyberQuest practice session file"),
            ({**good, "kind": "quiz"}, "Kind must be"),
            ({**good, "difficulty": "expert"}, "Difficulty must be"),
            ({**good, "est_minutes": 0}, "Estimated minutes"),
            ({**good, "topic": "NOPE-1"}, "choose a topic"),
            (broken_answer, "session content is not valid"),
        ]
        for payload, reason in cases:
            res = self._upload(payload)
            self.assertEqual(res.status_code, 200, reason)
            self.assertContains(res, reason)
        self.assertContains(self._upload(good, "session.txt"), "Choose a .json file")
        self.assertFalse(Scenario.objects.filter(status=Scenario.DRAFT).exists())
        self.assertFalse(StudioAuditLog.objects.exists())

    def test_imported_text_is_escaped_when_shown(self):
        payload = export_payload(Scenario.objects.get(slug="phish-01-choice"))
        payload["title"] = '<script>alert("x")</script>'
        res = self._upload(payload)
        page = self.client.get(res.url)
        self.assertNotContains(page, '<script>alert("x")</script>')
        self.assertContains(page, "&lt;script&gt;")
