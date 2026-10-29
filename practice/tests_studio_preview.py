"""Practice Studio, phase 5: preview the saved draft in the real player.

Preview requires Studio staff (404 for anyone else), uses the latest saved draft, awards
nothing, is the only page that may be framed (same origin only), and its answer key never
reaches the player or the student API."""

import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from courses.models import Course
from practice.graders import ANSWER_KEYS
from practice.models import Attempt, PracticeSession, Scenario
from practice.studio import services
from practice.studio.serializers import SessionSerializer
from practice.testing import answer_for, convert_all

User = get_user_model()


def member(name, group=None, **extra):
    user = User.objects.create_user(email=f"{name}@example.com", password="testpass123", username=name, **extra)
    if group:
        user.groups.add(Group.objects.get(name=group))
    return User.objects.get(pk=user.pk)


def keys(value):
    if isinstance(value, dict):
        return set(value).union(*(keys(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(keys(v) for v in value)) if value else set()
    return set()


class PreviewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        convert_all()
        cls.editor = member("ed", "Content Editor", is_staff=True)
        cls.topic = Course.objects.get(code="MOD-01")

    def setUp(self):
        self.client.force_login(self.editor)
        self.draft = services.from_template("incident", self.topic, self.editor)

    def save_draft(self, mutate, scenario=None):
        scenario = Scenario.objects.get(pk=(scenario or self.draft).pk)
        data = SessionSerializer.from_json(services.working_content(scenario))
        mutate(data)
        res = self.client.post(reverse("studio:save", args=[scenario.slug]),
                               json.dumps({"revision": scenario.draft_revision, "session": data}),
                               content_type="application/json")
        self.assertEqual(res.status_code, 200, res.content)

    def start(self, slug, preview=True, client=None):
        return (client or self.client).post(reverse("practice:api_start"), json.dumps({"scenario": slug, "preview": preview}),
                                            content_type="application/json")

    def urls(self, scenario=None):
        slug = (scenario or self.draft).slug
        return [reverse("studio:preview", args=[slug]), reverse("studio:play", args=[slug])]


class AccessTests(PreviewTestCase):
    def test_preview_is_studio_staff_only_and_404_for_everyone_else(self):
        for user in (member("student"), member("staffer", is_staff=True), member("mod", "Moderator", is_staff=True), None):
            client = Client()
            if user:
                client.force_login(user)
            for url in self.urls():
                self.assertEqual(client.get(url).status_code, 404, (user, url))
        for user in (self.editor, member("pub", "Content Publisher", is_staff=True)):
            self.client.force_login(user)
            for url in self.urls():
                res = self.client.get(url)
                self.assertEqual(res.status_code, 200, url)
                self.assertEqual(res["X-Robots-Tag"], "noindex, nofollow")
                self.assertIn("no-store", res["Cache-Control"])

    def test_the_preview_flag_does_nothing_for_students(self):
        student = Client()
        student.force_login(member("student"))
        self.assertEqual(self.start(self.draft.slug, client=student).status_code, 404)     # drafts stay hidden
        res = self.start("phish-01-choice", client=student)
        self.assertEqual(res.status_code, 201)
        self.assertFalse(res.json()["preview"])
        self.assertFalse(Attempt.objects.get(pk=res.json()["attempt_id"]).is_preview)


class DraftContentTests(PreviewTestCase):
    def test_preview_shows_the_latest_saved_draft_not_the_published_version(self):
        live = Scenario.objects.get(slug="phish-01-choice")
        published_intro = live.content["steps"][0]["intro"]
        self.save_draft(lambda d: d["steps"][0]["data"].update(intro="Draft intro for preview"), live)
        page = self.client.get(reverse("studio:play", args=[live.slug]))
        self.assertContains(page, "Draft intro for preview")
        self.assertContains(page, "PREVIEW — no XP, no stats")
        started = self.start(live.slug).json()
        self.assertEqual(started["content"]["steps"][0]["intro"], "Draft intro for preview")
        student = Client()
        student.force_login(member("student"))
        self.assertEqual(self.start(live.slug, preview=False, client=student).json()["content"]["steps"][0]["intro"],
                         published_intro)

    def test_preview_attempts_award_nothing_and_grade_on_their_draft_copy(self):
        res = self.start(self.draft.slug).json()
        attempt = Attempt.objects.get(pk=res["attempt_id"])
        self.assertTrue(attempt.is_preview)
        steps = Scenario.objects.get(pk=self.draft.pk).draft_content or Scenario.objects.get(pk=self.draft.pk).content
        # The draft changes after the preview started: the preview keeps grading on its copy.
        self.save_draft(lambda d: d["steps"][1]["data"].update(severity=0))
        for index, step in enumerate(steps["steps"]):
            if step["type"] == "story":
                continue
            answer = self.client.post(reverse("practice:api_answer", args=[attempt.pk]),
                                      json.dumps({"step": index, "answer": answer_for(step)}), content_type="application/json")
            self.assertTrue(answer.json()["correct"], step["type"])
        done = self.client.post(reverse("practice:api_complete", args=[attempt.pk])).json()
        self.editor.refresh_from_db()
        self.assertEqual((done["xp"], done["accuracy"], self.editor.xp), (0, 100, 0))
        self.assertFalse(PracticeSession.objects.exists())

    def test_restart_starts_a_fresh_preview_attempt(self):
        first = self.start(self.draft.slug).json()["attempt_id"]
        second = self.start(self.draft.slug).json()["attempt_id"]
        self.assertNotEqual(first, second)
        page = self.client.get(reverse("studio:preview", args=[self.draft.slug]))
        self.assertContains(page, 'id="st-restart"')
        self.assertContains(page, "Mobile (390 px)")
        self.assertContains(page, f'src="{reverse("studio:play", args=[self.draft.slug])}"')


class FramingTests(PreviewTestCase):
    def test_only_the_preview_player_may_be_framed_and_only_by_this_site(self):
        play = self.client.get(reverse("studio:play", args=[self.draft.slug]))
        self.assertEqual(play["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(play["Content-Security-Policy"], "frame-ancestors 'self'")
        student = Client()
        student.force_login(member("student"))
        others = [
            self.client.get(reverse("studio:preview", args=[self.draft.slug])),
            self.client.get(reverse("studio:steps", args=[self.draft.slug])),
            student.get(reverse("practice:session", args=["phish-01-choice"])),
            student.get(reverse("practice:center")),
            student.get("/"),
            Client().get(reverse("studio:play", args=[self.draft.slug])),            # the 404 for outsiders
        ]
        for res in others:
            self.assertEqual(res["X-Frame-Options"], "DENY", res.wsgi_request.path)
            self.assertEqual(res["Content-Security-Policy"], "frame-ancestors 'none'", res.wsgi_request.path)


class AnswerKeyTests(PreviewTestCase):
    def test_answer_key_is_beside_the_player_never_in_it_or_the_api(self):
        content = Scenario.objects.get(pk=self.draft.pk).content
        mcq = next(s for s in content["steps"] if s["type"] == "mcq")
        right_answer = mcq["options"][mcq["correct"]]
        wrong_answer = next(o for i, o in enumerate(mcq["options"]) if i != mcq["correct"])
        page = self.client.get(reverse("studio:preview", args=[self.draft.slug])).content.decode()
        self.assertIn("Answer key", page)
        key_html = page.split('class="st-key-list"', 1)[1]
        self.assertIn(right_answer, key_html)
        self.assertNotIn(wrong_answer, key_html)
        self.assertIn("Severity:", key_html)
        play = self.client.get(reverse("studio:play", args=[self.draft.slug])).content.decode()
        self.assertNotIn("Answer key", play)
        self.assertNotIn("st-key", play)
        for preview in (True, False):
            slug = self.draft.slug if preview else "phish-01-choice"
            started = self.start(slug, preview=preview).json()
            self.assertFalse(keys(started) & ANSWER_KEYS, preview)

    def test_preview_buttons_save_first(self):
        steps_page = self.client.get(reverse("studio:steps", args=[self.draft.slug]))
        self.assertContains(steps_page, f'href="{reverse("studio:preview", args=[self.draft.slug])}" class="ops-create" data-save-first')
        res = self.client.post(reverse("studio:basics", args=[self.draft.slug]), {
            "title": "Saved before preview", "topic": str(self.topic.pk), "difficulty": "beginner", "est_minutes": "10",
            "badge": "", "description": "", "revision": "0", "next": "preview"})
        self.assertRedirects(res, reverse("studio:preview", args=[self.draft.slug]))
        self.assertContains(self.client.get(reverse("studio:play", args=[self.draft.slug])), "Saved before preview")
        script = (Path(settings.BASE_DIR) / "practice/static/practice/studio/studio-editor.js").read_text(encoding="utf-8")
        self.assertIn("a[data-save-first]", script)
        self.assertIn("if (ok) window.location.href", script)
