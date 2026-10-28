"""Regression tests for the cyber defence curriculum, the Coming Soon lock and Phishing preservation."""

import json
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from courses.curriculum import ACTIVE_COURSES
from courses.models import Chapter, ChapterQuestion, ComicPanel, Course, CourseProgress, ReadingProgress
from courses.progress import completed_course_count, has_completed_all_courses, server_total_pages

User = get_user_model()

EXPECTED_ORDER = [
    "Cyber Security & Online Safety",
    "Phishing & Scam Prevention",
    "Password & Account Protection",
    "Malware & Ransomware Protection",
    "Wi-Fi & Network Safety",
    "Device & Personal Data Protection",
    "Social Media & Digital Privacy",
    "Cyber Attack Response & Recovery",
]
PHISHING_TEXT = "What is a phishing attack?\r\nPhishing refers to an attempt to steal sensitive information."


def sync():
    call_command("sync_curriculum", stdout=StringIO())


class CurriculumBase(TestCase):
    """Starts from the pre-curriculum catalogue (MOD-01 ... MOD-06), then syncs."""

    def setUp(self):
        self.phishing = Course.objects.create(
            code="MOD-01", title="Phishing attack", short_description="QUICK LEAARN",
            content=PHISHING_TEXT, order=0, is_published=True,
        )
        for code, title, order in [
            ("MOD-02", "Password Cracker", 2), ("MOD-03", "Network Defence", 3),
            ("MOD-04", "Cryptography", 4), ("MOD-05", "Steganography", 5), ("MOD-06", "OSINT", 6),
        ]:
            Course.objects.create(code=code, title=title, short_description=title, order=order,
                                  content=f"{title} original notes.", is_published=True)
        self.student = User.objects.create_user(
            email="learner@gmail.com", password="securepass1", username="learner", ethical_agreement=True,
        )
        self.admin = User.objects.create_user(
            email="chief@gmail.com", password="securepass1", username="chief",
            is_staff=True, is_superuser=True,
        )
        self.phishing_done = CourseProgress.objects.create(user=self.student, course=self.phishing)
        ReadingProgress.objects.create(user=self.student, course=self.phishing, last_page_index=4)
        sync()


class CurriculumOrderTests(CurriculumBase):
    def test_exactly_eight_active_courses_in_required_order(self):
        titles = list(Course.objects.active().order_by("order", "code").values_list("title", flat=True))
        self.assertEqual(titles, EXPECTED_ORDER)

    def test_course_list_renders_active_order_then_coming_soon(self):
        self.client.force_login(self.student)
        html = self.client.get(reverse("courses:intro")).content.decode()
        positions = [html.index(f'data-title="{t.replace("&", "&amp;")}"') for t in EXPECTED_ORDER]
        self.assertEqual(positions, sorted(positions))
        soon_at = html.index('id="soon-title"')
        self.assertGreater(soon_at, positions[-1])
        for title in ("Cryptography", "Steganography", "OSINT (Open-Source Intelligence)"):
            self.assertIn(title, html[soon_at:])
            # Locked books are not on the active shelf and have no open link.
            self.assertNotIn(f'data-title="{title}"', html)
        for code in ("MOD-04", "MOD-05", "MOD-06"):
            self.assertNotIn(reverse("courses:detail", args=[code]), html)

    def test_sync_is_idempotent_and_keeps_ids(self):
        ids = dict(Course.objects.values_list("code", "id"))
        counts = (Course.objects.count(), Chapter.objects.count(),
                  ComicPanel.objects.count(), ChapterQuestion.objects.count())
        sync()
        self.assertEqual(dict(Course.objects.values_list("code", "id")), ids)
        self.assertEqual(counts, (Course.objects.count(), Chapter.objects.count(),
                                  ComicPanel.objects.count(), ChapterQuestion.objects.count()))
        self.assertEqual(Course.objects.count(), 11)

    def test_existing_records_are_reused_for_password_and_network(self):
        self.assertEqual(Course.objects.get(code="MOD-02").title, "Password & Account Protection")
        self.assertEqual(Course.objects.get(code="MOD-03").title, "Wi-Fi & Network Safety")


class PhishingPreservationTests(CurriculumBase):
    def test_phishing_content_and_progress_are_untouched(self):
        course = Course.objects.get(pk=self.phishing.pk)
        self.assertEqual(course.code, "MOD-01")
        self.assertEqual(course.title, "Phishing & Scam Prevention")
        self.assertEqual(course.content, PHISHING_TEXT)
        self.assertEqual(course.short_description, "QUICK LEAARN")
        self.assertFalse(course.chapters.exists())
        self.assertTrue(CourseProgress.objects.filter(pk=self.phishing_done.pk).exists())
        self.assertEqual(ReadingProgress.objects.get(user=self.student, course=course).last_page_index, 4)

    def test_phishing_reader_and_mission_still_work(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("courses:detail", args=["MOD-01"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "What is a phishing attack?")
        self.assertContains(response, reverse("games:phishing_simulator"))
        from courses.progress import is_game_unlocked
        self.assertTrue(is_game_unlocked(self.student, "phishing_simulator"))

    def test_pdf_still_wins_over_chapters(self):
        # The real Phishing course is a PDF e-book; stray chapters must never replace it.
        Course.objects.filter(code="MOD-01").update(pdf_file="course_ebooks/course1.pdf")
        Chapter.objects.create(course=self.phishing, order=1, title="Draft chapter")
        course = Course.objects.get(code="MOD-01")
        self.assertTrue(course.uses_pdf())
        self.assertFalse(course.has_chapters)


class CourseContentTests(CurriculumBase):
    def test_every_replaced_course_has_real_chapters_and_quizzes(self):
        for spec in ACTIVE_COURSES:
            if spec.get("preserve"):
                continue
            course = Course.objects.get(code=spec["code"])
            chapters = list(course.chapters.all())
            self.assertGreaterEqual(len(chapters), 6, course.code)
            titles = [c.title for c in chapters]
            self.assertEqual(len(titles), len(set(titles)), course.code)
            for chapter in chapters:
                self.assertGreaterEqual(chapter.panels.count(), 4, chapter)
                questions = list(chapter.questions.all())
                self.assertGreaterEqual(len(questions), 2, chapter)
                for q in questions:
                    self.assertLess(q.correct_index, len(q.option_list()), q.prompt)
                    self.assertTrue(q.explanation)
            activities = ComicPanel.objects.filter(chapter__course=course, caption__startswith="Defence activity")
            self.assertGreaterEqual(activities.count(), 3, course.code)

    def test_comic_course_reader_shows_chapters_quiz_and_answers(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("courses:detail", args=["CQ-MALWARE"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Meet the Malware Family")
        self.assertContains(response, "Knowledge check")
        self.assertContains(response, 'class="cq-break"')
        self.assertContains(response, "Defence activity: Read the alert")

    def test_comic_course_can_be_completed(self):
        self.client.force_login(self.student)
        course = Course.objects.get(code="CQ-SAFETY")
        total = server_total_pages(course)
        self.assertGreaterEqual(total, 2)
        progress_url = reverse("courses:save_progress", args=[course.code])
        reached = 0
        while reached < total - 1:
            reached = min(reached + 2, total - 1)
            self.client.post(progress_url, data=json.dumps({"page_index": reached}),
                             content_type="application/json")
        ok = self.client.post(reverse("courses:mark_complete", args=[course.code]),
                              data=json.dumps({"pages_reached": total - 1}), content_type="application/json")
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(CourseProgress.objects.filter(user=self.student, course=course).exists())


class ComingSoonLockTests(CurriculumBase):
    LOCKED = ("MOD-04", "MOD-05", "MOD-06")

    def test_coming_soon_records_and_content_are_kept(self):
        for code in self.LOCKED:
            course = Course.objects.get(code=code)
            self.assertTrue(course.is_published)
            self.assertTrue(course.is_coming_soon)
            self.assertTrue(course.content.endswith("original notes."))
        self.assertEqual(Course.objects.coming_soon().count(), 3)

    def test_student_cannot_open_locked_course_by_url(self):
        self.client.force_login(self.student)
        for code in self.LOCKED:
            response = self.client.get(reverse("courses:detail", args=[code]))
            self.assertEqual(response.status_code, 403, code)
            self.assertContains(response, "Coming soon", status_code=403)
            self.assertNotContains(response, "original notes.", status_code=403)

    def test_student_cannot_use_progress_endpoints_or_ebook(self):
        self.client.force_login(self.student)
        for code in self.LOCKED:
            save = self.client.post(reverse("courses:save_progress", args=[code]),
                                    data=json.dumps({"page_index": 1}), content_type="application/json")
            done = self.client.post(reverse("courses:mark_complete", args=[code]),
                                    data=json.dumps({"pages_reached": 1}), content_type="application/json")
            ebook = self.client.get(reverse("courses:ebook", args=[code]))
            self.assertEqual((save.status_code, done.status_code, ebook.status_code), (403, 403, 403), code)
        self.assertFalse(ReadingProgress.objects.filter(course__is_coming_soon=True).exists())
        self.assertFalse(CourseProgress.objects.filter(course__is_coming_soon=True).exists())

    def test_learning_alias_route_is_locked_too(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get("/learning/cryptography/").status_code, 403)
        self.assertEqual(self.client.get("/learning/osint/").status_code, 403)
        self.assertEqual(self.client.get("/learning/phishing/").status_code, 200)

    def test_admin_can_still_preview_locked_course(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("courses:detail", args=["MOD-04"])).status_code, 200)

    def test_active_courses_are_not_locked(self):
        self.client.force_login(self.student)
        for spec in ACTIVE_COURSES:
            response = self.client.get(reverse("courses:detail", args=[spec["code"]]))
            self.assertEqual(response.status_code, 200, spec["code"])

    def test_coming_soon_courses_do_not_count_toward_progress(self):
        self.assertEqual(completed_course_count(self.student), (1, 8))
        CourseProgress.objects.create(user=self.student, course=Course.objects.get(code="MOD-04"))
        self.assertEqual(completed_course_count(self.student), (1, 8))
        for course in Course.objects.active():
            CourseProgress.objects.get_or_create(user=self.student, course=course)
        self.assertTrue(has_completed_all_courses(self.student))

    def test_active_missions_follow_the_eight_courses(self):
        from dashboard.utils import get_dashboard_context

        missions = get_dashboard_context(self.student)["active_missions"]
        self.assertEqual(
            [m["key"] for m in missions],
            ["online_safety", "phishing_simulator", "password_cracker", "malware_defense",
             "network_defense", "device_protection", "privacy_defense", "incident_response"],
        )
        cards = {m["key"]: m for m in missions}
        for soon in ("cryptography", "steganography", "osint"):
            self.assertNotIn(soon, cards)
        self.assertFalse(any(m["coming_soon"] for m in missions))
        self.assertEqual(
            [m["name"] for m in get_dashboard_context(self.student)["coming_soon_missions"]],
            ["Cryptography", "Steganography", "OSINT"],
        )
        self.assertFalse(cards["phishing_simulator"]["locked"])  # Phishing course done in setUp
        self.assertTrue(cards["online_safety"]["locked"])

        CourseProgress.objects.create(user=self.student, course=Course.objects.get(code="CQ-SAFETY"))
        cards = {m["key"]: m for m in get_dashboard_context(self.student)["active_missions"]}
        self.assertFalse(cards["online_safety"]["locked"])
        self.assertTrue(cards["malware_defense"]["locked"])

    def test_each_course_links_to_its_own_mission(self):
        from courses.progress import course_for_game

        expected = {
            "online_safety": "CQ-SAFETY", "phishing_simulator": "MOD-01", "password_cracker": "MOD-02",
            "malware_defense": "CQ-MALWARE", "network_defense": "MOD-03", "device_protection": "CQ-DEVICE",
            "privacy_defense": "CQ-PRIVACY", "incident_response": "CQ-RESPONSE",
        }
        for key, code in expected.items():
            self.assertEqual(course_for_game(key).code, code, key)
        for soon in ("cryptography", "steganography", "osint"):
            self.assertIsNone(course_for_game(soon), soon)

    def test_new_mission_plays_a_random_five_and_awards_xp(self):
        self.client.force_login(self.student)
        CourseProgress.objects.create(user=self.student, course=Course.objects.get(code="CQ-MALWARE"))
        url = reverse("games:malware_defense")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {"action": "start"})
        play = self.client.get(url)
        questions = play.context["questions"]
        self.assertEqual(len(questions), 5)
        post = {f"question_{q['id']}": str(q["correct_index"]) for q in questions}
        post["action"] = "submit"
        result = self.client.post(url, post)
        self.assertContains(result, "5 / 5")
        from games.models import GameAttempt
        attempt = GameAttempt.objects.get(user=self.student, game_key="malware_defense")
        self.assertEqual((attempt.score, attempt.status), (5, GameAttempt.STATUS_COMPLETED))
        self.assertGreater(attempt.xp_awarded, 0)

    def test_dashboard_bookshelf_lists_missions_then_locked_coming_soon(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("dashboard:home"))
        html = response.content.decode()
        shelf = html[html.index('id="active-missions"'):html.index('id="skill-matrix"')]
        titles = [book["title"] for book in response.context["books"]]
        self.assertEqual(titles[:8], ["Online Safety", "Phishing & Scams", "Account Protection", "Malware Defence",
                                      "Wi-Fi & Network", "Device Protection", "Privacy Shield", "Incident Response"])
        self.assertEqual(titles[8:], ["Cryptography", "Steganography", "OSINT"])
        positions = [shelf.index(t.replace("&", "&amp;")) for t in titles]
        self.assertEqual(positions, sorted(positions))
        # Three disabled Coming Soon buttons; none of their mission URLs are linked.
        self.assertEqual(shelf.count("disabled>Coming soon"), 3)
        for url_name in ("games:cryptography", "games:steganography", "games:osint"):
            self.assertNotIn(reverse(url_name), shelf)
            self.assertRedirects(self.client.get(reverse(url_name)), reverse("dashboard:home"),
                                 fetch_redirect_response=False)
        # Unlocked mission opens the game; locked one opens its course.
        self.assertIn(f'href="{reverse("games:phishing_simulator")}"', shelf)
        self.assertIn(f'href="{reverse("courses:detail", args=["CQ-SAFETY"])}"', shelf)

    def test_locked_new_mission_sends_student_to_its_course(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("games:incident_response"))
        self.assertRedirects(response, reverse("courses:intro"), fetch_redirect_response=False)
