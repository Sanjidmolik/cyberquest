import os
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.backends import EmailAuthBackend
from accounts.models import UserActivityDay
from achievements.models import Badge, UserBadge
from certificates.eligibility import REQUIRED_GAME_KEYS, is_eligible_for_certificate
from certificates.models import IssuedCertificate
from courses.models import Course, CourseProgress, ReadingProgress
from games.models import GameAttempt, Question, QuestionSet, QuestionSetItem
from practice.adaptive import get_cyber_dna
from games.registry import GAMES_REGISTRY
from practice.models import PracticeSession
from practice.scenarios import SCENARIOS, get_scenario
from notifications.models import Notification
from pages.models import ContactMessage
from question_bank.models import QuestionBank

User = get_user_model()


class AdminCommandCenterAccessTests(TestCase):
    def test_command_center_fields_keep_a_keyboard_focus_ring(self):
        from django.conf import settings
        css = (settings.BASE_DIR / "dashboard/static/dashboard/css/ops.css").read_text(encoding="utf-8")
        hidden = css.find(".ops-filters input:focus")
        visible = css.find(".ops-filters input:focus-visible")
        self.assertGreater(hidden, -1)
        self.assertGreater(visible, hidden)
        self.assertIn("outline: 2px solid var(--focus)", css)
        self.assertIn(".ops-search input:focus-visible", css)
        self.assertIn(".ops-panel textarea:focus-visible", css)
    def setUp(self):
        self.student = User.objects.create_user(email="student@example.com", password="pass12345")
        self.staff = User.objects.create_user(
            email="staff@example.com", password="pass12345", is_staff=True
        )
        self.superuser = User.objects.create_superuser(email="root@example.com", password="pass12345")

    def test_anonymous_is_redirected(self):
        response = self.client.get(reverse("ops:overview"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login/", response.url)

    def test_student_and_staff_are_forbidden(self):
        for user in (self.student, self.staff):
            self.client.force_login(user)
            response = self.client.get(reverse("ops:overview"))
            self.assertEqual(response.status_code, 403)

    def test_superuser_can_open_command_pages(self):
        self.client.force_login(self.superuser)
        names = [
            "overview", "students", "courses", "games", "practice",
            "questions", "review", "certificates", "achievements",
            "notifications", "contact", "analytics", "settings", "search", "leaderboard",
        ]
        for name in names:
            response = self.client.get(reverse(f"ops:{name}"))
            self.assertEqual(response.status_code, 200, name)
        html = self.client.get(reverse("ops:overview")).content.decode()
        self.assertNotIn("SECRET_KEY", html)
        self.assertNotIn("password", html.lower())

    def test_contact_resolve_and_unsafe_notification(self):
        self.client.force_login(self.superuser)
        message = ContactMessage.objects.create(name="Ada", email="ada@example.com", message="Hello")
        response = self.client.post(reverse("ops:resolve_contact", args=[message.pk]), {"resolved": "1"})
        self.assertEqual(response.status_code, 302)
        message.refresh_from_db()
        self.assertTrue(message.is_resolved)

        response = self.client.post(reverse("ops:notifications"), {
            "email": self.student.email,
            "message": "Review your progress",
            "link_url": "https://evil.example/phish",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notification links must stay on this site.")
        self.assertFalse(Notification.objects.filter(user=self.student).exists())

        response = self.client.post(reverse("ops:notifications"), {
            "email": self.student.email,
            "message": "Review your progress",
            "link_url": "/dashboard/",
        })
        self.assertEqual(response.status_code, 302)
        note = Notification.objects.get(user=self.student)
        self.assertEqual(note.link_url, "/dashboard/")

    def test_approve_only_review_banks(self):
        self.client.force_login(self.superuser)
        bank = QuestionBank.objects.create(
            title="Phish bank",
            domain="phishing_simulator",
            source_content="Source text long enough.",
            status=QuestionBank.STATUS_REVIEW,
        )
        qset = QuestionSet.objects.create(
            course="phishing_simulator",
            set_number=1,
            set_type=QuestionSet.SET_TYPE_NORMAL,
            question_bank=bank,
            status=QuestionSet.STATUS_REVIEW,
        )
        response = self.client.post(reverse("ops:approve_bank", args=[bank.pk]))
        self.assertEqual(response.status_code, 302)
        bank.refresh_from_db()
        qset.refresh_from_db()
        self.assertEqual(bank.status, QuestionBank.STATUS_APPROVED)
        self.assertEqual(qset.status, QuestionSet.STATUS_APPROVED)

        draft = QuestionBank.objects.create(
            title="Draft bank",
            domain="phishing_simulator",
            source_content="Another source.",
            status=QuestionBank.STATUS_DRAFT,
        )
        self.client.post(reverse("ops:approve_bank", args=[draft.pk]))
        draft.refresh_from_db()
        self.assertEqual(draft.status, QuestionBank.STATUS_DRAFT)


class CourseManagementTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(email="learner@example.com", password="pass12345")
        self.staff = User.objects.create_user(
            email="editor@example.com", password="pass12345", is_staff=True
        )
        self.superuser = User.objects.create_superuser(email="ops@example.com", password="pass12345")
        self.published = Course.objects.create(
            code="MOD-01", title="Phishing basics", short_description="Spot fake mail",
            content="Lesson text", order=1, is_published=True,
        )
        self.draft = Course.objects.create(
            code="MOD-02", title="Draft lab", short_description="Not ready",
            content="", order=2, is_published=False,
        )

    def test_anonymous_student_and_staff_cannot_manage_courses(self):
        list_url = reverse("ops:courses")
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login/", response.url)

        for user in (self.student, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(list_url).status_code, 403)
            self.assertEqual(self.client.get(reverse("ops:course_create")).status_code, 403)
            self.assertEqual(self.client.get(reverse("ops:course_edit", args=["MOD-01"])).status_code, 403)
            self.assertEqual(
                self.client.post(reverse("ops:course_publish", args=["MOD-01"]), {"action": "unpublish"}).status_code,
                403,
            )
            self.published.refresh_from_db()
            self.assertTrue(self.published.is_published)

    def test_superuser_lists_searches_and_filters(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("ops:courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Phishing basics")
        self.assertContains(response, "Draft lab")
        self.assertContains(response, "Create course")

        found = self.client.get(reverse("ops:courses"), {"q": "phish"})
        self.assertContains(found, "MOD-01")
        self.assertNotContains(found, "MOD-02")

        drafts = self.client.get(reverse("ops:courses"), {"status": "draft"})
        self.assertContains(drafts, "MOD-02")
        self.assertNotContains(drafts, "MOD-01")

    def test_create_edit_and_reject_invalid_course(self):
        self.client.force_login(self.superuser)
        pdf = SimpleUploadedFile("guide.pdf", b"%PDF-1.4\n", content_type="application/pdf")
        created = self.client.post(reverse("ops:course_create"), {
            "code": "MOD-09",
            "title": "New lesson",
            "short_description": "A short summary",
            "content": "Read this",
            "pdf_file": pdf,
            "order": "3",
        })
        self.assertEqual(created.status_code, 302)
        course = Course.objects.get(code="MOD-09")
        self.assertEqual(course.title, "New lesson")
        self.assertFalse(course.is_published)
        self.assertTrue(course.uses_pdf())

        bad = self.client.post(reverse("ops:course_create"), {
            "code": "MOD-09",
            "title": "",
            "short_description": "Again",
            "content": "",
            "order": "-1",
        })
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(Course.objects.filter(code="MOD-09").count(), 1)

        not_pdf = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")
        rejected = self.client.post(reverse("ops:course_edit", args=["MOD-09"]), {
            "code": "MOD-09",
            "title": "New lesson",
            "short_description": "A short summary",
            "content": "Read this",
            "pdf_file": not_pdf,
            "order": "3",
        })
        self.assertEqual(rejected.status_code, 200)
        course.refresh_from_db()
        self.assertTrue(course.pdf_file.name.endswith(".pdf"))

        saved = self.client.post(reverse("ops:course_edit", args=["MOD-09"]), {
            "code": "MOD-09",
            "title": "Updated lesson",
            "short_description": "A short summary",
            "content": "Read this",
            "order": "4",
            "is_published": "on",
        })
        self.assertRedirects(saved, reverse("ops:course_edit", args=["MOD-09"]))
        course.refresh_from_db()
        self.assertEqual(course.title, "Updated lesson")
        self.assertTrue(course.is_published)
        self.assertEqual(course.order, 4)

    def test_course_thumbnail_upload_display_and_rejection(self):
        from io import BytesIO
        from PIL import Image
        self.client.force_login(self.superuser)
        buffer = BytesIO()
        Image.new("RGB", (12, 12), (20, 40, 80)).save(buffer, format="PNG")
        png = SimpleUploadedFile("cover.png", buffer.getvalue(), content_type="image/png")
        created = self.client.post(reverse("ops:course_create"), {
            "code": "MOD-11",
            "title": "Thumb lesson",
            "short_description": "Has a picture",
            "content": "Read this",
            "thumbnail": png,
            "order": "5",
            "is_published": "on",
        })
        self.assertEqual(created.status_code, 302)
        course = Course.objects.get(code="MOD-11")
        self.assertTrue(course.thumbnail.name.endswith(".png"))
        self.assertTrue(course.safe_thumbnail_url())
        self.assertTrue(course.pdf_file.name in ("", None) or not course.uses_pdf())

        fake = SimpleUploadedFile("cover.png", b"MZ\x90\x00not-an-image", content_type="image/png")
        rejected = self.client.post(reverse("ops:course_edit", args=["MOD-11"]), {
            "code": "MOD-11",
            "title": "Thumb lesson",
            "short_description": "Has a picture",
            "content": "Read this",
            "thumbnail": fake,
            "order": "5",
            "is_published": "on",
        })
        self.assertEqual(rejected.status_code, 200)
        course.refresh_from_db()
        self.assertTrue(course.thumbnail.name.endswith(".png"))

        self.client.force_login(self.student)
        page = self.client.get(reverse("courses:intro"))
        self.assertContains(page, course.safe_thumbnail_url())
        self.assertContains(page, "course-placeholder.svg")

    def test_publish_requires_post_and_stays_on_site(self):
        self.client.force_login(self.superuser)
        blocked = self.client.get(reverse("ops:course_publish", args=["MOD-02"]))
        self.assertEqual(blocked.status_code, 405)
        self.draft.refresh_from_db()
        self.assertFalse(self.draft.is_published)

        published = self.client.post(reverse("ops:course_publish", args=["MOD-02"]), {"action": "publish"})
        self.assertRedirects(published, reverse("ops:courses"))
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.is_published)

        away = self.client.post(reverse("ops:course_publish", args=["MOD-02"]), {
            "action": "unpublish",
            "next": "https://evil.example/phish",
        })
        self.assertRedirects(away, reverse("ops:courses"))
        self.draft.refresh_from_db()
        self.assertFalse(self.draft.is_published)


class QuestionBankManagementTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(email="learner2@example.com", password="pass12345")
        self.staff = User.objects.create_user(
            email="editor2@example.com", password="pass12345", is_staff=True
        )
        self.superuser = User.objects.create_superuser(email="ops2@example.com", password="pass12345")
        self.bank = QuestionBank.objects.create(
            title="Phish review bank",
            description="Mailbox drills",
            domain="phishing_simulator",
            source_content="Only trust the real sender domain.",
            status=QuestionBank.STATUS_REVIEW,
        )
        self.question = Question.objects.create(
            course="phishing_simulator",
            prompt="Which message is safe to open?",
            options=["The bank email", "A lookalike domain", "A surprise invoice", "A password reset you did not request"],
            correct_index=0,
            explanation="The first option matches the real sender.",
            question_type=Question.TYPE_MCQ,
            difficulty=Question.DIFF_BEGINNER,
            generated_by_ai=True,
            is_active=True,
        )
        self.qset = QuestionSet.objects.create(
            course="phishing_simulator",
            set_number=1,
            set_type=QuestionSet.SET_TYPE_NORMAL,
            question_bank=self.bank,
            status=QuestionSet.STATUS_REVIEW,
            is_active=True,
        )
        QuestionSetItem.objects.create(question_set=self.qset, question=self.question, order=1)

    def test_access_is_superuser_only(self):
        urls = [
            reverse("ops:questions"),
            reverse("ops:question_bank", args=[self.bank.pk]),
            reverse("ops:question_detail", args=[self.question.pk]),
            reverse("ops:review"),
        ]
        response = self.client.get(urls[0])
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login/", response.url)
        for user in (self.student, self.staff):
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403, url)
            self.assertEqual(
                self.client.post(
                    reverse("ops:question_visibility", args=[self.question.pk]),
                    {"action": "hide"},
                ).status_code,
                403,
            )
        self.question.refresh_from_db()
        self.assertTrue(self.question.is_active)

    def test_list_search_filter_and_open_bank(self):
        other = QuestionBank.objects.create(
            title="Crypto vault",
            description="Keys",
            domain="cryptography",
            source_content="Ciphers.",
            status=QuestionBank.STATUS_APPROVED,
        )
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:questions"))
        self.assertContains(page, "Phish review bank")
        self.assertContains(page, "Phishing")
        self.assertContains(page, "1 question")

        found = self.client.get(reverse("ops:questions"), {"q": "mailbox"})
        self.assertContains(found, "Phish review bank")
        self.assertNotContains(found, "Crypto vault")

        games = self.client.get(reverse("ops:questions"), {"domain": "cryptography"})
        self.assertContains(games, "Crypto vault")
        self.assertNotContains(games, "Phish review bank")

        waiting = self.client.get(reverse("ops:questions"), {"status": QuestionBank.STATUS_REVIEW})
        self.assertContains(waiting, "Phish review bank")
        self.assertNotContains(waiting, "Crypto vault")

        detail = self.client.get(reverse("ops:question_bank", args=[self.bank.pk]))
        self.assertContains(detail, "Which message is safe to open?")
        self.assertContains(detail, "Needs review")
        self.assertEqual(self.client.get(reverse("ops:question_bank", args=[99999])).status_code, 404)
        self.assertEqual(other.status, QuestionBank.STATUS_APPROVED)

    def test_question_bank_pagination_keeps_the_game_filter(self):
        for number in range(21):
            QuestionBank.objects.create(
                title=f"Crypto page {number} a&b",
                description="Keys",
                domain="cryptography",
                source_content="Ciphers.",
                status=QuestionBank.STATUS_APPROVED,
            )
        self.client.force_login(self.superuser)
        first = self.client.get(reverse("ops:questions"), {"domain": "cryptography", "q": "a&b"})
        self.assertContains(first, "domain=cryptography")
        self.assertContains(first, "q=a%26b")
        self.assertNotContains(first, "Phish review bank")
        second = self.client.get(
            reverse("ops:questions"),
            {"domain": "cryptography", "q": "a&b", "page": "2"},
        )
        self.assertContains(second, "Crypto page")
        self.assertNotContains(second, "Phish review bank")
        self.assertContains(second, "Page 2 of")

    def test_question_display_edit_hide_and_live_lock(self):
        self.client.force_login(self.superuser)
        shown = self.client.get(reverse("ops:question_detail", args=[self.question.pk]))
        self.assertContains(shown, "The bank email")
        self.assertContains(shown, "correct")
        self.assertContains(shown, "Save question")

        saved = self.client.post(reverse("ops:question_detail", args=[self.question.pk]), {
            "prompt": "Which mailbox is genuine?",
            "option_1": "The bank email",
            "option_2": "A lookalike domain",
            "option_3": "A surprise invoice",
            "option_4": "A password reset you did not request",
            "correct_choice": "0",
            "explanation": "Match the real sender.",
            "difficulty": "beginner",
        })
        self.assertRedirects(saved, reverse("ops:question_detail", args=[self.question.pk]))
        self.question.refresh_from_db()
        self.assertEqual(self.question.prompt, "Which mailbox is genuine?")
        self.assertTrue(self.question.manually_edited)

        self.bank.status = QuestionBank.STATUS_APPROVED
        self.bank.save(update_fields=["status"])
        self.qset.status = QuestionSet.STATUS_APPROVED
        self.qset.save(update_fields=["status"])
        locked = self.client.post(reverse("ops:question_detail", args=[self.question.pk]), {
            "prompt": "Changed while live",
            "option_1": "A",
            "option_2": "B",
            "correct_choice": "0",
            "explanation": "No",
            "difficulty": "beginner",
        })
        self.assertRedirects(locked, reverse("ops:question_detail", args=[self.question.pk]))
        self.question.refresh_from_db()
        self.assertEqual(self.question.prompt, "Which mailbox is genuine?")

        hidden = self.client.post(
            reverse("ops:question_visibility", args=[self.question.pk]),
            {"action": "hide"},
        )
        self.assertRedirects(hidden, reverse("ops:question_detail", args=[self.question.pk]))
        self.question.refresh_from_db()
        self.assertFalse(self.question.is_active)
        self.assertEqual(
            self.client.get(reverse("ops:question_visibility", args=[self.question.pk])).status_code,
            405,
        )
        self.assertEqual(self.client.get(reverse("ops:question_detail", args=[99999])).status_code, 404)

    def test_archive_and_review_actions_stay_post_only(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse("ops:archive_bank", args=[self.bank.pk])).status_code, 405)
        archived = self.client.post(reverse("ops:archive_bank", args=[self.bank.pk]), {"action": "archive"})
        self.assertRedirects(archived, reverse("ops:question_bank", args=[self.bank.pk]))
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.status, QuestionBank.STATUS_ARCHIVED)

        review_bank = QuestionBank.objects.create(
            title="Waiting bank",
            domain="osint",
            source_content="Public sources.",
            status=QuestionBank.STATUS_REVIEW,
        )
        review_set = QuestionSet.objects.create(
            course="osint",
            set_number=1,
            set_type=QuestionSet.SET_TYPE_NORMAL,
            question_bank=review_bank,
            status=QuestionSet.STATUS_REVIEW,
        )
        rejected = self.client.post(reverse("ops:reject_set", args=[review_set.pk]))
        self.assertRedirects(rejected, reverse("ops:review"))
        review_set.refresh_from_db()
        self.assertEqual(review_set.status, QuestionSet.STATUS_REJECTED)

        secure = self.client.__class__(enforce_csrf_checks=True)
        secure.force_login(self.superuser)
        blocked = secure.post(reverse("ops:archive_bank", args=[review_bank.pk]), {"action": "archive"})
        self.assertEqual(blocked.status_code, 403)
        review_bank.refresh_from_db()
        self.assertEqual(review_bank.status, QuestionBank.STATUS_REVIEW)


class PracticeScenarioManagementTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(email="learner3@example.com", password="pass12345")
        self.staff = User.objects.create_user(
            email="editor3@example.com", password="pass12345", is_staff=True
        )
        self.superuser = User.objects.create_superuser(email="ops3@example.com", password="pass12345")
        self.key = "phishing_microsoft_disable"
        self.session = PracticeSession.objects.create(
            user=self.student,
            domain="phishing",
            activity_type="simulation",
            scenario_key=self.key,
            difficulty="beginner",
            score=80,
            max_score=100,
            status="completed",
        )
        PracticeSession.objects.create(
            user=self.staff,
            domain="phishing",
            activity_type="simulation",
            scenario_key=self.key,
            difficulty="beginner",
            score=10,
            max_score=100,
            status="completed",
        )

    def test_access_is_superuser_only(self):
        list_url = reverse("ops:practice")
        detail_url = reverse("ops:practice_scenario", args=[self.key])
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login/", response.url)
        for user in (self.student, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(list_url).status_code, 403)
            self.assertEqual(self.client.get(detail_url).status_code, 403)

    def test_list_filters_and_student_usage(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:practice"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Suspicious email reported by employee")
        self.assertContains(page, "development team")
        self.assertContains(page, get_scenario("network_dns_beacon")["title"])
        self.assertEqual(len(page.context["scenarios"]), len(SCENARIOS))

        phishing = self.client.get(reverse("ops:practice"), {"domain": "phishing"})
        self.assertContains(phishing, "Suspicious email reported by employee")
        self.assertNotContains(phishing, get_scenario("network_dns_beacon")["title"])

        incidents = self.client.get(reverse("ops:practice"), {"type": "incident"})
        self.assertNotContains(incidents, "Suspicious email reported by employee")
        self.assertContains(incidents, get_scenario("phishing_invoice_attachment")["title"])

        found = self.client.get(reverse("ops:practice"), {"q": "CQ-PH-001"})
        self.assertContains(found, "Suspicious email reported by employee")
        self.assertNotContains(found, get_scenario("network_dns_beacon")["title"])

        ignored = self.client.get(reverse("ops:practice"), {"domain": "not-a-domain", "type": "hack"})
        self.assertContains(ignored, "Suspicious email reported by employee")
        self.assertContains(ignored, get_scenario("crypto_message_audit")["title"])

    def test_detail_shows_configuration_and_usage(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:practice_scenario", args=[self.key]))
        self.assertContains(page, "Spot a lookalike sender")
        self.assertContains(page, "Inspect Sender")
        self.assertContains(page, "Needed before the decision")
        self.assertContains(page, "Recommended")
        self.assertEqual(page.context["scenario"]["usage"]["completed"], 1)
        self.assertEqual(page.context["scenario"]["usage"]["students"], 1)
        self.assertEqual(page.context["scenario"]["usage"]["avg_score"], 80)
        self.assertNotContains(page, self.staff.email)
        self.assertEqual(self.client.get(reverse("ops:practice_scenario", args=["missing-scenario"])).status_code, 404)
        self.session.refresh_from_db()
        self.assertEqual(self.session.score, 80)
        self.assertEqual(get_scenario(self.key)["title"], "Suspicious email reported by employee")

    def test_there_is_no_edit_action(self):
        self.client.force_login(self.superuser)
        blocked = self.client.post(reverse("ops:practice_scenario", args=[self.key]), {"title": "Changed"})
        self.assertEqual(blocked.status_code, 405)
        self.assertEqual(get_scenario(self.key)["title"], "Suspicious email reported by employee")
        secure = self.client.__class__(enforce_csrf_checks=True)
        secure.force_login(self.superuser)
        denied = secure.post(reverse("ops:practice_scenario", args=[self.key]), {"title": "Changed"})
        self.assertEqual(denied.status_code, 403)
        self.session.refresh_from_db()
        self.assertEqual(self.session.score, 80)


class GameManagementTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(email="learner4@example.com", password="pass12345")
        self.staff = User.objects.create_user(
            email="editor4@example.com", password="pass12345", is_staff=True
        )
        self.superuser = User.objects.create_superuser(email="ops4@example.com", password="pass12345")
        self.bank = QuestionBank.objects.create(
            title="Phishing game bank",
            domain="phishing_simulator",
            source_content="Lookalike domains.",
            status=QuestionBank.STATUS_APPROVED,
        )
        question = Question.objects.create(
            course="phishing_simulator",
            prompt="Which sender is real?",
            options=["The company domain", "A lookalike"],
            correct_index=0,
            explanation="Match the real domain.",
            difficulty=Question.DIFF_BEGINNER,
            is_active=True,
        )
        qset = QuestionSet.objects.create(
            course="phishing_simulator",
            set_number=1,
            set_type=QuestionSet.SET_TYPE_NORMAL,
            question_bank=self.bank,
            status=QuestionSet.STATUS_APPROVED,
            is_active=True,
        )
        QuestionSetItem.objects.create(question_set=qset, question=question, order=1)
        GameAttempt.objects.create(
            user=self.student, game_key="phishing_simulator", score=2, total_questions=5, xp_awarded=40,
        )
        GameAttempt.objects.create(
            user=self.student, game_key="phishing_simulator", score=4, total_questions=5, xp_awarded=0,
        )
        GameAttempt.objects.create(
            user=self.staff, game_key="phishing_simulator", score=5, total_questions=5, xp_awarded=100,
        )
        GameAttempt.objects.create(
            user=self.superuser, game_key="phishing_simulator", score=0, total_questions=5, xp_awarded=0,
        )
        Question.objects.create(
            course="phishing_simulator",
            prompt="Hidden from students",
            options=["Shown", "Hidden"],
            correct_index=1,
            explanation="Inactive questions are not served.",
            is_active=False,
        )
        GameAttempt.objects.create(
            user=self.student, game_key="whack_a_phish", score=1, total_questions=1,
        )

    def test_access_is_superuser_only(self):
        listing = reverse("ops:games")
        detail = reverse("ops:game", args=["phishing_simulator"])
        response = self.client.get(listing)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login/", response.url)
        for user in (self.student, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(listing).status_code, 403)
            self.assertEqual(self.client.get(detail).status_code, 403)

    def test_catalog_search_filter_and_bank_link(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:games"))
        self.assertEqual(len(page.context["games"]), len(GAMES_REGISTRY))
        self.assertContains(page, "Phishing Simulator")
        self.assertContains(page, "Phishing game bank")
        self.assertContains(page, "Steganography Hunt")

        found = self.client.get(reverse("ops:games"), {"q": "steganography"})
        self.assertEqual([row["key"] for row in found.context["games"]], ["steganography"])
        self.assertContains(found, "Steganography Hunt")

        one = self.client.get(reverse("ops:games"), {"game": "network_defense"})
        self.assertEqual(len(one.context["games"]), 1)
        self.assertEqual(one.context["games"][0]["key"], "network_defense")

        by_bank = self.client.get(reverse("ops:games"), {"bank": self.bank.pk})
        self.assertEqual([row["key"] for row in by_bank.context["games"]], ["phishing_simulator"])

        ignored = self.client.get(reverse("ops:games"), {
            "game": "not-a-game",
            "bank": "99999",
            "status": "retired",
        })
        self.assertEqual(len(ignored.context["games"]), len(GAMES_REGISTRY))
        self.assertNotContains(ignored, "Whack-a-Phish")

        by_label = self.client.get(reverse("ops:games"), {"q": "Password Security"})
        self.assertEqual([row["key"] for row in by_label.context["games"]], ["password_cracker"])

        clash = self.client.get(reverse("ops:games"), {"game": "network_defense", "bank": self.bank.pk})
        self.assertEqual(clash.context["games"], [])

    def test_detail_usage_and_question_pool(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:game", args=["phishing_simulator"]))
        game = page.context["game"]
        self.assertEqual(game["usable_questions"], 1)
        self.assertEqual(game["bank_title"], "Phishing game bank")
        self.assertEqual(game["bank_label"], "Phishing")
        self.assertEqual(game["question_count"], 1)
        self.assertEqual(game["usage"]["attempts"], 2)
        self.assertEqual(game["usage"]["completed"], 2)
        self.assertEqual(game["usage"]["students"], 1)
        self.assertEqual(game["usage"]["replays"], 1)
        self.assertEqual(game["usage"]["avg_score"], 3)
        self.assertEqual(game["usage"]["avg_percent"], 60)
        self.assertEqual(game["usage"]["first_avg_percent"], 40)
        self.assertEqual(game["usage"]["xp"], 40)
        self.assertContains(page, "Phishing game bank")
        self.assertContains(page, "Question bank")
        self.assertContains(page, "does not add XP")
        self.assertNotContains(page, self.staff.email)
        self.assertEqual(self.client.get(reverse("ops:game", args=["whack_a_phish"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("ops:game", args=["missing-game"])).status_code, 404)
        built_in = self.client.get(reverse("ops:game", args=["steganography"]))
        self.assertContains(built_in, "does not use a question bank")
        self.assertFalse(built_in.context["game"]["has_bank"])
        self.assertEqual(GameAttempt.objects.filter(user=self.student, game_key="phishing_simulator").count(), 2)
        from dashboard.ops import game_rows
        analytics = {row["key"]: row for row in game_rows()}
        self.assertEqual(analytics["phishing_simulator"]["attempts"], 4)
        self.assertIn("whack_a_phish", analytics)

    def test_there_is_no_edit_action(self):
        self.client.force_login(self.superuser)
        blocked = self.client.post(reverse("ops:game", args=["phishing_simulator"]), {"name": "Changed"})
        self.assertEqual(blocked.status_code, 405)
        self.assertEqual(self.client.post(reverse("ops:games"), {"name": "Changed"}).status_code, 405)
        secure = self.client.__class__(enforce_csrf_checks=True)
        secure.force_login(self.superuser)
        denied = secure.post(reverse("ops:game", args=["phishing_simulator"]), {"name": "Changed"})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(secure.post(reverse("ops:games"), {"name": "Changed"}).status_code, 403)
        saved = GameAttempt.objects.get(user=self.student, xp_awarded=40)
        self.assertEqual(saved.score, 2)
        self.assertEqual(saved.xp_awarded, 40)
        self.assertEqual(
            next(item["name"] for item in GAMES_REGISTRY if item["key"] == "phishing_simulator"),
            "Phishing Simulator",
        )


class StudentManagementTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email="ada@example.com",
            password="pass12345",
            username="ada",
            full_name="Ada Learner",
        )
        self.student.xp = 350
        self.student.level = 4
        self.student.totp_secret = "TOTPSECRETVALUE"
        self.student.last_active_date = timezone.localdate()
        self.student.save(update_fields=["xp", "level", "totp_secret", "last_active_date"])
        self.other = User.objects.create_user(
            email="quiet@example.com", password="pass12345", username="quiet", full_name="Quiet Learner",
        )
        self.staff = User.objects.create_user(
            email="staff5@example.com", password="pass12345", is_staff=True,
        )
        self.superuser = User.objects.create_superuser(email="ops5@example.com", password="pass12345")
        self.done = Course.objects.create(
            code="MOD-S", title="Finished module", content="Hello", order=1, is_published=True,
        )
        self.started = Course.objects.create(
            code="MOD-T", title="Opened module", content="Hello", order=2, is_published=True,
        )
        CourseProgress.objects.create(user=self.student, course=self.done)
        ReadingProgress.objects.create(user=self.student, course=self.started, last_page_index=0)
        GameAttempt.objects.create(
            user=self.student, game_key="phishing_simulator", score=4, total_questions=5, xp_awarded=80,
        )
        GameAttempt.objects.create(
            user=self.student, game_key="phishing_simulator", score=2, total_questions=5, xp_awarded=0,
        )
        PracticeSession.objects.create(
            user=self.student, domain="phishing", activity_type="simulation",
            scenario_key="phishing_microsoft_disable", difficulty="beginner",
            score=80, max_score=100, status="completed",
        )
        PracticeSession.objects.create(
            user=self.student, domain="phishing", activity_type="simulation",
            scenario_key="phishing_microsoft_disable", difficulty="beginner",
            score=10, max_score=100, status="in_progress",
        )
        badge = Badge.objects.create(code="ops_reader", name="Careful Reader", description="Finished a module")
        UserBadge.objects.create(user=self.student, badge=badge)
        self.certificate = IssuedCertificate.objects.create(
            user=self.student,
            certificate_id="CQ-TEST-STUDENT",
            verification_token="secret-token-should-not-render",
            recipient_name="Ada Learner",
            score=88,
            issued_at=timezone.now(),
        )

    def test_access_is_superuser_only(self):
        listing = reverse("ops:students")
        detail = reverse("ops:student", args=[self.student.pk])
        response = self.client.get(listing)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login/", response.url)
        self.assertEqual(self.client.get(detail).status_code, 302)
        for user in (self.student, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(listing).status_code, 403)
            self.assertEqual(self.client.get(detail).status_code, 403)
            self.assertEqual(
                self.client.post(reverse("ops:student_status", args=[self.student.pk]), {"action": "deactivate"}).status_code,
                403,
            )
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)

    def test_directory_search_and_filters(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:students"))
        self.assertContains(page, "Ada Learner")
        self.assertContains(page, "ada@example.com")
        self.assertContains(page, "Quiet Learner")
        self.assertNotContains(page, self.staff.email)
        emails = [row.email for row in page.context["page_obj"].object_list]
        self.assertNotIn(self.superuser.email, emails)
        self.assertNotIn(self.staff.email, emails)
        self.assertEqual(page.context["summary"]["total"], 2)
        self.assertEqual(page.context["summary"]["active"], 2)
        listed = {row.email: row for row in page.context["page_obj"].object_list}
        self.assertEqual(listed["ada@example.com"].course_done, 1)
        self.assertEqual(listed["ada@example.com"].progress_percent, 50)

        by_name = self.client.get(reverse("ops:students"), {"q": "Ada"})
        self.assertContains(by_name, "ada@example.com")
        self.assertNotContains(by_name, "quiet@example.com")
        by_user = self.client.get(reverse("ops:students"), {"q": "quiet"})
        self.assertContains(by_user, "quiet@example.com")
        self.assertNotContains(by_user, "ada@example.com")

        by_level = self.client.get(reverse("ops:students"), {"level": "4"})
        self.assertEqual([row.email for row in by_level.context["page_obj"].object_list], ["ada@example.com"])
        recent = self.client.get(reverse("ops:students"), {"activity": "recent"})
        self.assertContains(recent, "ada@example.com")
        self.assertNotContains(recent, "quiet@example.com")
        never = self.client.get(reverse("ops:students"), {"activity": "never"})
        self.assertContains(never, "quiet@example.com")
        self.assertNotContains(never, "ada@example.com")

        ignored = self.client.get(reverse("ops:students"), {
            "status": "banned", "level": "high", "activity": "hacked",
        })
        self.assertEqual(ignored.context["page_obj"].paginator.count, 2)

    def test_detail_uses_existing_records(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:student", args=[self.student.pk]))
        profile = page.context["profile"]
        self.assertEqual(profile["learning"]["started"], 2)
        self.assertEqual(profile["learning"]["completed"], 1)
        self.assertEqual(profile["learning"]["average"], 75)
        self.assertEqual(profile["games"]["attempts"], 2)
        self.assertEqual(profile["games"]["games"], 1)
        self.assertEqual(profile["games"]["avg_score"], 3)
        self.assertEqual(profile["games"]["avg_percent"], 60)
        self.assertEqual(profile["games"]["xp"], 80)
        self.assertEqual(profile["games"]["best"][0]["percent"], 80)
        self.assertEqual(profile["practice"]["sessions"], 2)
        self.assertEqual(profile["practice"]["completed"], 1)
        self.assertEqual(profile["practice"]["avg_score"], 80)
        self.assertEqual(profile["practice"]["dna"]["overall"], get_cyber_dna(self.student)["overall"])
        self.assertEqual(profile["xp_info"]["xp"], 350)
        self.assertEqual(profile["xp_info"]["level"], 4)
        self.assertEqual(profile["xp_info"]["into_level"], 50)
        self.assertEqual(profile["badge_count"], 1)
        self.assertEqual(profile["certificate"]["certificate_id"], "CQ-TEST-STUDENT")
        self.assertEqual(profile["eligible"], is_eligible_for_certificate(self.student))
        self.assertContains(page, "Careful Reader")
        self.assertContains(page, "CQ-TEST-STUDENT")
        self.assertContains(page, "Finished module")
        self.assertNotContains(page, "secret-token-should-not-render")
        self.assertNotContains(page, "TOTPSECRETVALUE")
        self.assertNotContains(page, self.student.password)
        self.assertNotContains(page, "quiet@example.com")
        self.assertEqual(self.client.get(reverse("ops:student", args=[self.staff.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("ops:student", args=[self.superuser.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("ops:student", args=[999999])).status_code, 404)

    def test_status_action_is_post_and_does_not_touch_progress(self):
        self.client.force_login(self.superuser)
        blocked = self.client.get(reverse("ops:student_status", args=[self.student.pk]))
        self.assertEqual(blocked.status_code, 405)
        password_hash = self.student.password
        self.client.post(reverse("ops:student_status", args=[self.student.pk]), {
            "action": "deactivate",
            "xp": "99999",
            "level": "1",
            "is_active": "true",
        })
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertEqual(self.student.xp, 350)
        self.assertEqual(self.student.level, 4)
        self.assertEqual(self.student.password, password_hash)
        self.assertEqual(GameAttempt.objects.get(user=self.student, xp_awarded=80).score, 4)
        self.assertIsNone(EmailAuthBackend().authenticate(None, email="ada@example.com", password="pass12345"))

        self.client.post(reverse("ops:student_status", args=[self.student.pk]), {"action": "nope", "xp": "1"})
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)
        self.assertEqual(self.student.xp, 350)

        self.client.post(reverse("ops:student_status", args=[self.student.pk]), {"action": "activate"})
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)
        self.assertEqual(
            EmailAuthBackend().authenticate(None, email="ada@example.com", password="pass12345").pk,
            self.student.pk,
        )
        self.assertEqual(
            self.client.post(reverse("ops:student_status", args=[self.staff.pk]), {"action": "deactivate"}).status_code,
            404,
        )
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

        secure = self.client.__class__(enforce_csrf_checks=True)
        secure.force_login(self.superuser)
        denied = secure.post(reverse("ops:student_status", args=[self.student.pk]), {"action": "deactivate"})
        self.assertEqual(denied.status_code, 403)
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)


class CertificateManagementTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email="certlearner@example.com",
            password="pass12345",
            username="certlearner",
            full_name="Cert Learner",
        )
        self.other = User.objects.create_user(
            email="nocert@example.com",
            password="pass12345",
            username="nocert",
            full_name="No Cert",
        )
        self.staff = User.objects.create_user(
            email="certstaff@example.com", password="pass12345", is_staff=True,
        )
        self.superuser = User.objects.create_superuser(email="certops@example.com", password="pass12345")
        for key in REQUIRED_GAME_KEYS:
            GameAttempt.objects.create(user=self.student, game_key=key, score=5, total_questions=5)
        self.old = IssuedCertificate.objects.create(
            user=self.other,
            certificate_id="CQ-2020-OLD00001",
            verification_token="old-token-must-stay-hidden",
            recipient_name="No Cert",
            score=70,
            issued_at=timezone.now() - timedelta(days=40),
        )

    def test_access_is_superuser_only(self):
        listing = reverse("ops:certificates")
        detail = reverse("ops:certificate", args=[self.old.pk])
        issue = reverse("ops:certificate_issue", args=[self.student.pk])
        response = self.client.get(listing)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login/", response.url)
        for user in (self.student, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(listing).status_code, 403)
            self.assertEqual(self.client.get(detail).status_code, 403)
            self.assertEqual(self.client.post(issue).status_code, 403)
        self.assertFalse(IssuedCertificate.objects.filter(user=self.student).exists())

    def test_directory_search_and_filters(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:certificates"))
        self.assertContains(page, "CQ-2020-OLD00001")
        self.assertContains(page, "nocert@example.com")
        self.assertContains(page, "Cert Learner")
        self.assertEqual(page.context["summary"]["issued"], 0)
        self.assertEqual(page.context["summary"]["waiting"], 1)
        self.assertNotContains(page, "old-token-must-stay-hidden")

        by_id = self.client.get(reverse("ops:certificates"), {"q": "OLD00001"})
        self.assertContains(by_id, "No Cert")
        by_user = self.client.get(reverse("ops:certificates"), {"q": "nocert"})
        self.assertEqual(list(by_user.context["page_obj"].object_list), [self.old])
        missing = self.client.get(reverse("ops:certificates"), {"q": "certlearner"})
        self.assertEqual(list(missing.context["page_obj"].object_list), [])

        recent = self.client.get(reverse("ops:certificates"), {"window": "7"})
        self.assertEqual(list(recent.context["page_obj"].object_list), [])
        incomplete = self.client.get(reverse("ops:certificates"), {"readiness": "incomplete"})
        self.assertContains(incomplete, "CQ-2020-OLD00001")
        ready = self.client.get(reverse("ops:certificates"), {"readiness": "ready"})
        self.assertEqual(list(ready.context["page_obj"].object_list), [])
        ignored = self.client.get(reverse("ops:certificates"), {"window": "forever", "readiness": "bogus"})
        self.assertContains(ignored, "CQ-2020-OLD00001")

    def test_detail_eligibility_and_verification_link(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:certificate", args=[self.old.pk]))
        certificate = page.context["certificate"]
        self.assertFalse(certificate["ready"])
        self.assertFalse(certificate["eligibility"]["eligible"])
        self.assertEqual(
            certificate["eligibility"]["eligible"],
            is_eligible_for_certificate(self.other),
        )
        self.assertContains(page, "CQ-2020-OLD00001")
        self.assertContains(page, "nocert@example.com")
        self.assertContains(page, "Not eligible")
        self.assertNotContains(page, "View verification")
        self.assertNotContains(page, "old-token-must-stay-hidden")
        self.assertNotContains(page, self.other.password)
        self.assertEqual(self.client.get(reverse("ops:certificate", args=[999999])).status_code, 404)

    def test_issue_uses_existing_workflow_and_blocks_duplicates(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse("ops:certificate_issue", args=[self.student.pk])).status_code, 405)
        issued = self.client.post(reverse("ops:certificate_issue", args=[self.student.pk]), {
            "score": "1",
            "certificate_id": "CQ-HACK",
            "eligible": "false",
            "force": "1",
        })
        certificate = IssuedCertificate.objects.get(user=self.student)
        self.assertRedirects(issued, reverse("ops:certificate", args=[certificate.pk]))
        self.assertTrue(certificate.pdf_file)
        self.assertEqual(certificate.score, 100)
        self.assertNotEqual(certificate.certificate_id, "CQ-HACK")
        self.assertRegex(certificate.certificate_id, r"^CQ-\d{4}-[0-9A-F]{8}$")

        again = self.client.post(reverse("ops:certificate_issue", args=[self.student.pk]), {
            "score": "1",
            "force": "1",
        })
        self.assertRedirects(again, reverse("ops:certificate", args=[certificate.pk]))
        self.assertEqual(IssuedCertificate.objects.filter(user=self.student).count(), 1)
        certificate.refresh_from_db()
        self.assertEqual(certificate.score, 100)

        detail = self.client.get(reverse("ops:certificate", args=[certificate.pk]))
        self.assertContains(detail, "View verification")
        self.assertContains(detail, certificate.certificate_id)
        self.assertIn(f"/verify/{certificate.certificate_id}/", detail.context["certificate"]["verify_url"])
        self.assertTrue(detail.context["certificate"]["eligibility"]["eligible"])
        self.assertNotContains(detail, certificate.verification_token)

        public = self.client.get(reverse("certificate_verify", args=[certificate.certificate_id]))
        self.assertContains(public, "CERTIFICATE VERIFIED")
        self.assertContains(public, certificate.certificate_id)
        self.assertNotContains(public, self.student.email)
        missing = self.client.get(reverse("certificate_verify", args=["CQ-2099-DEADBEEF"]))
        self.assertContains(missing, "INVALID CERTIFICATE")

        lonely = User.objects.create_user(email="lonely@example.com", password="pass12345")
        denied = self.client.post(reverse("ops:certificate_issue", args=[lonely.pk]), {"score": "100"})
        self.assertRedirects(denied, reverse("ops:certificates"))
        self.assertFalse(IssuedCertificate.objects.filter(user=lonely).exists())
        self.assertEqual(
            self.client.post(reverse("ops:certificate_issue", args=[self.staff.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(reverse("ops:certificate_issue", args=[999999])).status_code,
            404,
        )

        secure = self.client.__class__(enforce_csrf_checks=True)
        secure.force_login(self.superuser)
        blocked = secure.post(reverse("ops:certificate_issue", args=[lonely.pk]))
        self.assertEqual(blocked.status_code, 403)


class AchievementManagementTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email="badgelearner@example.com",
            password="pass12345",
            username="badgelearner",
            full_name="Badge Learner",
        )
        self.other = User.objects.create_user(
            email="nobadge@example.com", password="pass12345", username="nobadge",
        )
        self.staff = User.objects.create_user(
            email="badgestaff@example.com", password="pass12345", is_staff=True,
        )
        self.superuser = User.objects.create_superuser(email="badgeops@example.com", password="pass12345")
        self.badge = Badge.objects.get(code="first_steps")
        self.hidden = Badge.objects.create(
            code="ops_hidden_badge",
            name="Hidden Trophy",
            description="A retired badge",
            icon_emoji="🗄️",
            is_active=False,
        )
        self.award = UserBadge.objects.create(user=self.student, badge=self.badge)
        UserBadge.objects.filter(pk=self.award.pk).update(earned_at=timezone.now() - timedelta(days=3))
        self.award.refresh_from_db()
        UserBadge.objects.create(user=self.staff, badge=self.badge)

    def test_access_is_superuser_only(self):
        listing = reverse("ops:achievements")
        detail = reverse("ops:achievement", args=[self.badge.pk])
        response = self.client.get(listing)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login/", response.url)
        self.assertEqual(self.client.get(detail).status_code, 302)
        for user in (self.student, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(listing).status_code, 403)
            self.assertEqual(self.client.get(detail).status_code, 403)
            self.assertEqual(self.client.post(listing).status_code, 403)
        self.assertEqual(UserBadge.objects.filter(badge=self.badge).count(), 2)

    def test_directory_search_filters_and_student_counts(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:achievements"))
        self.assertContains(page, "First Steps")
        self.assertContains(page, "Completed your first training game.")
        self.assertContains(page, "Hidden Trophy")
        self.assertNotContains(page, "first_steps")
        self.assertNotContains(page, self.student.password)
        first = next(row for row in page.context["badges"] if row.pk == self.badge.pk)
        self.assertEqual(first.earned, 1)
        self.assertEqual(page.context["summary"]["holders"], 1)
        self.assertEqual(page.context["summary"]["awards"], 1)
        self.assertEqual(page.context["summary"]["students"], 2)
        self.assertContains(page, self.award.earned_at.date().isoformat())

        by_name = self.client.get(reverse("ops:achievements"), {"q": "First Steps"})
        self.assertContains(by_name, "First Steps")
        self.assertNotContains(by_name, "Hidden Trophy")
        by_description = self.client.get(reverse("ops:achievements"), {"q": "retired badge"})
        self.assertEqual([row.pk for row in by_description.context["badges"]], [self.hidden.pk])

        active = self.client.get(reverse("ops:achievements"), {"status": "active"})
        self.assertNotContains(active, "Hidden Trophy")
        self.assertContains(active, "First Steps")
        inactive = self.client.get(reverse("ops:achievements"), {"status": "inactive"})
        self.assertEqual([row.pk for row in inactive.context["badges"]], [self.hidden.pk])
        ignored = self.client.get(reverse("ops:achievements"), {"status": "archived"})
        self.assertContains(ignored, "Hidden Trophy")
        self.assertContains(ignored, "First Steps")

    def test_detail_lists_student_earners_only(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:achievement", args=[self.badge.pk]))
        self.assertContains(page, "Badge Learner")
        self.assertContains(page, "badgelearner@example.com")
        self.assertContains(page, "Completed your first training game.")
        self.assertEqual(page.context["earned"], 1)
        emails = [row.user.email for row in page.context["page_obj"]]
        self.assertEqual(emails, ["badgelearner@example.com"])
        self.assertNotContains(page, self.student.password)
        self.assertContains(page, reverse("ops:student", args=[self.student.pk]))
        self.assertEqual(self.client.get(reverse("ops:achievement", args=[999999])).status_code, 404)

    def test_pages_do_not_award_or_change_badges(self):
        from achievements.checks import check_and_award_badges

        self.client.force_login(self.superuser)
        before = list(UserBadge.objects.filter(user=self.student).values_list("badge_id", "earned_at"))
        self.student.refresh_from_db()
        xp = self.student.xp
        self.assertEqual(self.client.post(reverse("ops:achievements"), {"earned": "99"}).status_code, 405)
        self.assertEqual(
            self.client.post(reverse("ops:achievement", args=[self.badge.pk]), {"earned": "99"}).status_code,
            405,
        )
        self.client.get(reverse("ops:achievements"))
        self.client.get(reverse("ops:achievement", args=[self.badge.pk]))
        self.assertEqual(
            list(UserBadge.objects.filter(user=self.student).values_list("badge_id", "earned_at")),
            before,
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.xp, xp)

        GameAttempt.objects.create(
            user=self.other, game_key="phishing_simulator", score=1, total_questions=5,
        )
        awarded = check_and_award_badges(self.other)
        self.assertIn("first_steps", [badge.code for badge in awarded])
        self.assertEqual(check_and_award_badges(self.other), [])
        self.assertEqual(UserBadge.objects.filter(user=self.other).count(), len(awarded))


class LeaderboardManagementTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.ada = User.objects.create_user(
            email="ada.rank@example.com",
            password="pass12345",
            username="ada_rank",
            full_name="Ada Rank",
            xp=300,
            level=4,
            last_active_date=today,
        )
        self.ben = User.objects.create_user(
            email="ben.rank@example.com",
            password="pass12345",
            username="ben_rank",
            full_name="Ben Rank",
            xp=100,
            level=2,
        )
        self.cara = User.objects.create_user(
            email="cara.rank@example.com",
            password="pass12345",
            username="cara_rank",
            full_name="Cara Rank",
            xp=100,
            level=2,
        )
        self.inactive = User.objects.create_user(
            email="inactive.rank@example.com",
            password="pass12345",
            username="inactive_rank",
            xp=999,
            is_active=False,
        )
        self.blank = User.objects.create_user(
            email="blank.rank@example.com",
            password="pass12345",
            username="",
            xp=888,
        )
        self.staff = User.objects.create_user(
            email="coach.rank@example.com",
            password="pass12345",
            username="coach_rank",
            xp=500,
            level=6,
            is_staff=True,
            last_active_date=today,
        )
        self.superuser = User.objects.create_superuser(email="lbops@example.com", password="pass12345")

    def test_access_is_superuser_only(self):
        url = reverse("ops:leaderboard")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login/", response.url)
        for user in (self.ada, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {"xp": "1"}).status_code, 403)
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.xp, 300)

    def test_ranking_ties_and_exclusions(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:leaderboard"))
        rows = list(page.context["page_obj"].object_list)
        self.assertEqual(
            [user.username for user in rows],
            ["coach_rank", "ada_rank", "ben_rank", "cara_rank"],
        )
        self.assertEqual([user.board_rank for user in rows], [1, 2, 3, 4])
        self.assertLess(self.ben.pk, self.cara.pk)
        self.assertEqual(page.context["summary"]["total"], 4)
        self.assertEqual(page.context["summary"]["highest"], 500)
        self.assertEqual(page.context["summary"]["average"], 250)
        self.assertContains(page, "300")
        self.assertContains(page, ">4<")
        self.assertContains(page, reverse("ops:student", args=[self.ada.pk]))
        self.assertNotContains(page, reverse("ops:student", args=[self.staff.pk]))
        self.assertNotContains(page, "inactive_rank")
        self.assertNotContains(page, "blank.rank@example.com")
        self.assertNotContains(page, self.ada.password)
        self.assertNotContains(page, "totp")

    def test_search_and_filters_keep_overall_rank(self):
        self.client.force_login(self.superuser)
        by_name = self.client.get(reverse("ops:leaderboard"), {"q": "Ada Rank"})
        found = list(by_name.context["page_obj"].object_list)
        self.assertEqual([user.username for user in found], ["ada_rank"])
        self.assertEqual(found[0].board_rank, 2)
        self.assertEqual(by_name.context["summary"]["total"], 4)
        self.assertContains(by_name, "overall position")

        by_level = self.client.get(reverse("ops:leaderboard"), {"level": "2"})
        self.assertEqual(
            [user.username for user in by_level.context["page_obj"].object_list],
            ["ben_rank", "cara_rank"],
        )
        self.assertEqual(
            [user.board_rank for user in by_level.context["page_obj"].object_list],
            [3, 4],
        )
        quiet = self.client.get(reverse("ops:leaderboard"), {"activity": "never"})
        self.assertEqual(
            [user.username for user in quiet.context["page_obj"].object_list],
            ["ben_rank", "cara_rank"],
        )
        ignored = self.client.get(reverse("ops:leaderboard"), {"level": "high", "activity": "forever"})
        self.assertEqual(len(ignored.context["page_obj"].object_list), 4)

    def test_matches_student_leaderboard_and_rejects_changes(self):
        self.client.force_login(self.ada)
        public = self.client.get(reverse("leaderboard:list"))
        self.assertEqual(public.context["my_rank"], 2)
        public_names = [user.username for user in public.context["top_users"]]
        self.assertEqual(public_names[:2], ["coach_rank", "ada_rank"])
        self.assertNotIn("inactive_rank", public_names)
        self.assertNotIn("", public_names)

        self.client.force_login(self.superuser)
        before = (self.ada.xp, self.ada.level)
        denied = self.client.post(reverse("ops:leaderboard"), {"xp": "1", "level": "9", "rank": "1"})
        self.assertEqual(denied.status_code, 405)
        self.ada.refresh_from_db()
        self.assertEqual((self.ada.xp, self.ada.level), before)
        admin = self.client.get(reverse("ops:leaderboard"))
        admin_names = [user.username for user in admin.context["page_obj"].object_list]
        self.assertEqual(admin_names[0], public_names[0])
        self.assertEqual(admin_names[1], public_names[1])
        tied = [name for name in admin_names if name in {"ben_rank", "cara_rank"}]
        self.assertEqual(tied, ["ben_rank", "cara_rank"])


class NotificationManagementTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email="note.student@example.com",
            password="pass12345",
            username="notestudent",
            full_name="Note Student",
        )
        self.staff = User.objects.create_user(
            email="note.staff@example.com", password="pass12345", is_staff=True,
        )
        self.superuser = User.objects.create_superuser(email="noteops@example.com", password="pass12345")
        self.unread = Notification.objects.create(
            user=self.student, message="Finish the phishing module", link_url="/dashboard/",
        )
        self.read = Notification.objects.create(
            user=self.student, message="Badge unlocked", link_url="", is_read=True,
        )
        self.old = Notification.objects.create(
            user=self.student, message="Old reminder", link_url="",
        )
        Notification.objects.filter(pk=self.old.pk).update(created_at=timezone.now() - timedelta(days=40))

    def test_access_is_superuser_only(self):
        listing = reverse("ops:notifications")
        detail = reverse("ops:notification", args=[self.unread.pk])
        response = self.client.get(listing)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login/", response.url)
        for user in (self.student, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(listing).status_code, 403)
            self.assertEqual(self.client.get(detail).status_code, 403)
            self.assertEqual(self.client.post(listing, {"email": self.student.email, "message": "Nope"}).status_code, 403)
        self.assertEqual(Notification.objects.filter(message="Nope").count(), 0)
        self.unread.refresh_from_db()
        self.assertFalse(self.unread.is_read)

    def test_directory_search_filters_and_counts(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:notifications"))
        self.assertContains(page, "Finish the phishing module")
        self.assertContains(page, "note.student@example.com")
        self.assertContains(page, "Unread")
        self.assertContains(page, "Read")
        self.assertEqual(page.context["summary"]["total"], 3)
        self.assertEqual(page.context["summary"]["unread"], 2)
        self.assertEqual(page.context["summary"]["read"], 1)
        self.assertNotContains(page, self.student.password)

        by_message = self.client.get(reverse("ops:notifications"), {"q": "phishing"})
        self.assertEqual([row.pk for row in by_message.context["page_obj"].object_list], [self.unread.pk])
        by_name = self.client.get(reverse("ops:notifications"), {"q": "Note Student"})
        self.assertEqual(by_name.context["page_obj"].paginator.count, 3)
        unread = self.client.get(reverse("ops:notifications"), {"status": "unread"})
        self.assertEqual(unread.context["page_obj"].paginator.count, 2)
        read = self.client.get(reverse("ops:notifications"), {"status": "read"})
        self.assertEqual([row.pk for row in read.context["page_obj"].object_list], [self.read.pk])
        recent = self.client.get(reverse("ops:notifications"), {"window": "7"})
        self.assertNotIn(self.old.pk, [row.pk for row in recent.context["page_obj"].object_list])
        ignored = self.client.get(reverse("ops:notifications"), {"status": "archived", "window": "forever"})
        self.assertEqual(ignored.context["page_obj"].paginator.count, 3)

    def test_detail_does_not_mark_read(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:notification", args=[self.unread.pk]))
        self.assertContains(page, "Finish the phishing module")
        self.assertContains(page, "note.student@example.com")
        self.assertContains(page, "Unread")
        self.assertContains(page, reverse("ops:student", args=[self.student.pk]))
        self.assertContains(page, "/dashboard/")
        self.unread.refresh_from_db()
        self.assertFalse(self.unread.is_read)
        self.assertEqual(self.client.get(reverse("ops:notification", args=[999999])).status_code, 404)
        self.assertEqual(self.client.post(reverse("ops:notification", args=[self.unread.pk]), {"is_read": "1"}).status_code, 405)
        self.unread.refresh_from_db()
        self.assertFalse(self.unread.is_read)

    def test_send_validates_recipient_link_and_csrf(self):
        self.client.force_login(self.superuser)
        sent = self.client.post(reverse("ops:notifications"), {
            "email": self.student.email,
            "message": "Review your progress",
            "link_url": "/dashboard/",
            "is_read": "true",
        })
        self.assertRedirects(sent, reverse("ops:notifications"))
        note = Notification.objects.get(message="Review your progress")
        self.assertEqual(note.user_id, self.student.pk)
        self.assertFalse(note.is_read)
        self.assertEqual(note.link_url, "/dashboard/")

        blocked = self.client.post(reverse("ops:notifications"), {
            "email": self.student.email,
            "message": "Go away",
            "link_url": "https://evil.example/phish",
        })
        self.assertEqual(blocked.status_code, 200)
        self.assertContains(blocked, "Notification links must stay on this site.")
        self.assertFalse(Notification.objects.filter(message="Go away").exists())

        for email in (self.staff.email, "missing@example.com", "one@example.com,two@example.com"):
            self.client.post(reverse("ops:notifications"), {"email": email, "message": "Bulk or unknown"})
        self.assertFalse(Notification.objects.filter(message="Bulk or unknown").exists())

        secure = self.client.__class__(enforce_csrf_checks=True)
        secure.force_login(self.superuser)
        denied = secure.post(reverse("ops:notifications"), {
            "email": self.student.email,
            "message": "No token",
        })
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(Notification.objects.filter(message="No token").exists())

    def test_student_read_and_redirect_behavior_stays(self):
        unsafe = Notification.objects.create(
            user=self.student,
            message="Stored outside link",
            link_url="https://malicious-site.example/phish",
        )
        self.client.force_login(self.superuser)
        admin_page = self.client.get(reverse("ops:notification", args=[unsafe.pk]))
        self.assertContains(admin_page, "https://malicious-site.example/phish")
        self.assertNotContains(admin_page, 'href="https://malicious-site.example/phish"')
        unsafe.refresh_from_db()
        self.assertFalse(unsafe.is_read)

        self.client.force_login(self.student)
        opened = self.client.get(reverse("notifications:redirect", args=[unsafe.pk]))
        self.assertRedirects(opened, reverse("dashboard:home"), fetch_redirect_response=False)
        unsafe.refresh_from_db()
        self.assertTrue(unsafe.is_read)
        self.assertEqual(unsafe.link_url, "https://malicious-site.example/phish")

        fresh = Notification.objects.create(user=self.student, message="Still unread", link_url="/dashboard/")
        self.client.force_login(self.superuser)
        self.client.get(reverse("ops:notifications"))
        self.client.get(reverse("ops:notification", args=[fresh.pk]))
        fresh.refresh_from_db()
        self.assertFalse(fresh.is_read)

        self.client.force_login(self.student)
        self.client.get(reverse("notifications:list"))
        fresh.refresh_from_db()
        self.assertTrue(fresh.is_read)
        followed = self.client.get(reverse("notifications:redirect", args=[fresh.pk]))
        self.assertRedirects(followed, "/dashboard/", fetch_redirect_response=False)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    BREVO_API_KEY="",
)
class ContactManagementTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(email="contact.student@example.com", password="pass12345")
        self.staff = User.objects.create_user(
            email="contact.staff@example.com", password="pass12345", is_staff=True,
        )
        self.superuser = User.objects.create_superuser(email="contactops@example.com", password="pass12345")
        self.open_message = ContactMessage.objects.create(
            name="Ada Writer",
            email="ada.writer@example.com",
            message="The course reader stops on page two. " + ("detail " * 30),
        )
        self.resolved = ContactMessage.objects.create(
            name="Ben Reader",
            email="ben.reader@example.com",
            message="Thanks, the certificate downloaded.",
            is_resolved=True,
        )
        self.old = ContactMessage.objects.create(
            name="Old Sender",
            email="old.sender@example.com",
            message="An older note about billing.",
        )
        ContactMessage.objects.filter(pk=self.old.pk).update(submitted_at=timezone.now() - timedelta(days=40))

    def test_access_is_superuser_only(self):
        listing = reverse("ops:contact")
        detail = reverse("ops:contact_message", args=[self.open_message.pk])
        resolve = reverse("ops:resolve_contact", args=[self.open_message.pk])
        reply = reverse("ops:reply_contact", args=[self.open_message.pk])
        self.assertEqual(listing, "/admin-dashboard/contacts/")
        response = self.client.get(listing)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login/", response.url)
        self.assertEqual(self.client.post(reply, {"reply": "We can help."}).status_code, 302)
        for user in (self.student, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(listing).status_code, 403)
            self.assertEqual(self.client.get(detail).status_code, 403)
            self.assertEqual(self.client.post(resolve, {"resolved": "1"}).status_code, 403)
            self.assertEqual(self.client.post(reply, {"reply": "We can help."}).status_code, 403)
        self.assertEqual(len(mail.outbox), 0)
        self.open_message.refresh_from_db()
        self.assertFalse(self.open_message.is_resolved)
        self.client.logout()
        legacy = self.client.get("/admin-dashboard/contact/")
        self.assertRedirects(legacy, "/admin-dashboard/contacts/", fetch_redirect_response=False)

    def test_inbox_search_filters_and_counts(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:contact"))
        self.assertContains(page, "Ada Writer")
        self.assertContains(page, "ada.writer@example.com")
        self.assertContains(page, "Open")
        self.assertContains(page, "Resolved")
        self.assertNotContains(page, "detail " * 30)
        self.assertEqual(page.context["summary"]["total"], 3)
        self.assertEqual(page.context["summary"]["open"], 2)
        self.assertEqual(page.context["summary"]["resolved"], 1)
        self.assertNotContains(page, self.student.password)

        by_name = self.client.get(reverse("ops:contact"), {"q": "Ada Writer"})
        self.assertEqual([row.pk for row in by_name.context["page_obj"].object_list], [self.open_message.pk])
        by_body = self.client.get(reverse("ops:contact"), {"q": "certificate downloaded"})
        self.assertEqual([row.pk for row in by_body.context["page_obj"].object_list], [self.resolved.pk])
        opened = self.client.get(reverse("ops:contact"), {"state": "open"})
        self.assertEqual(opened.context["page_obj"].paginator.count, 2)
        closed = self.client.get(reverse("ops:contact"), {"state": "resolved"})
        self.assertEqual([row.pk for row in closed.context["page_obj"].object_list], [self.resolved.pk])
        recent = self.client.get(reverse("ops:contact"), {"window": "7"})
        self.assertNotIn(self.old.pk, [row.pk for row in recent.context["page_obj"].object_list])
        ignored = self.client.get(reverse("ops:contact"), {"state": "archived", "window": "forever"})
        self.assertEqual(ignored.context["page_obj"].paginator.count, 3)

    def test_detail_resolve_and_reopen(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:contact_message", args=[self.open_message.pk]))
        self.assertContains(page, "detail " * 20)
        self.assertContains(page, "ada.writer@example.com")
        self.assertContains(page, "Open")
        self.open_message.refresh_from_db()
        self.assertFalse(self.open_message.is_resolved)
        self.assertEqual(self.client.get(reverse("ops:contact_message", args=[999999])).status_code, 404)
        self.assertEqual(self.client.post(reverse("ops:contact_message", args=[self.open_message.pk])).status_code, 405)

        resolved = self.client.post(reverse("ops:resolve_contact", args=[self.open_message.pk]), {"resolved": "1"})
        self.assertRedirects(resolved, reverse("ops:contact_message", args=[self.open_message.pk]))
        self.assertNotIn("course reader", resolved.url)
        self.open_message.refresh_from_db()
        self.assertTrue(self.open_message.is_resolved)

        reopened = self.client.post(reverse("ops:resolve_contact", args=[self.open_message.pk]), {"resolved": "0"})
        self.assertRedirects(reopened, reverse("ops:contact_message", args=[self.open_message.pk]))
        self.open_message.refresh_from_db()
        self.assertFalse(self.open_message.is_resolved)

        ignored = self.client.post(reverse("ops:resolve_contact", args=[self.open_message.pk]), {"resolved": "maybe"})
        self.assertRedirects(ignored, reverse("ops:contact_message", args=[self.open_message.pk]))
        self.open_message.refresh_from_db()
        self.assertFalse(self.open_message.is_resolved)
        self.assertEqual(self.client.get(reverse("ops:resolve_contact", args=[self.open_message.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse("ops:resolve_contact", args=[999999]), {"resolved": "1"}).status_code, 404)

        secure = self.client.__class__(enforce_csrf_checks=True)
        secure.force_login(self.superuser)
        denied = secure.post(reverse("ops:resolve_contact", args=[self.open_message.pk]), {"resolved": "1"})
        self.assertEqual(denied.status_code, 403)
        self.open_message.refresh_from_db()
        self.assertFalse(self.open_message.is_resolved)

    @override_settings(DEFAULT_FROM_EMAIL="ops@example.com")
    def test_reply_sends_mail_without_changing_the_message(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:contact_message", args=[self.open_message.pk]))
        self.assertContains(page, "Reply by email")
        self.assertContains(page, "ada.writer@example.com")
        sent = self.client.post(reverse("ops:reply_contact", args=[self.open_message.pk]), {
            "reply": "The reader issue is fixed in the next lesson.",
            "email": "attacker@example.com",
        })
        self.assertRedirects(
            sent,
            reverse("ops:contact_message", args=[self.open_message.pk]),
            fetch_redirect_response=False,
        )
        followed = self.client.get(sent.url)
        self.assertContains(followed, "Reply sent to ada.writer@example.com.")
        self.assertEqual(len(mail.outbox), 1)
        letter = mail.outbox[0]
        self.assertEqual(letter.from_email, "ops@example.com")
        self.assertEqual(letter.to, ["ada.writer@example.com"])
        self.assertEqual(letter.subject, "Reply from CyberQuest")
        self.assertIn("The reader issue is fixed in the next lesson.", letter.body)
        self.assertNotIn("attacker@example.com", letter.to)
        self.open_message.refresh_from_db()
        self.assertFalse(self.open_message.is_resolved)
        self.assertTrue(self.open_message.message.startswith("The course reader stops"))
        self.assertEqual(self.client.get(reverse("ops:reply_contact", args=[self.open_message.pk])).status_code, 405)
        self.assertEqual(self.client.post(reverse("ops:reply_contact", args=[999999]), {"reply": "Hi"}).status_code, 404)

    @override_settings(DEFAULT_FROM_EMAIL="ops@example.com")
    def test_reply_rejects_invalid_input_and_failed_delivery(self):
        self.client.force_login(self.superuser)
        url = reverse("ops:reply_contact", args=[self.open_message.pk])
        blank = self.client.post(url, {"reply": "   "})
        self.assertRedirects(blank, reverse("ops:contact_message", args=[self.open_message.pk]), fetch_redirect_response=False)
        self.assertContains(self.client.get(blank.url), "Enter a reply before sending.")
        self.assertEqual(len(mail.outbox), 0)
        long = self.client.post(url, {"reply": "x" * 4001})
        self.assertRedirects(long, reverse("ops:contact_message", args=[self.open_message.pk]), fetch_redirect_response=False)
        self.assertContains(self.client.get(long.url), "Keep the reply under 4000 characters.")
        self.assertEqual(len(mail.outbox), 0)
        ContactMessage.objects.filter(pk=self.open_message.pk).update(email="not-an-email")
        invalid = self.client.post(url, {"reply": "Hello there"})
        self.assertRedirects(invalid, reverse("ops:contact_message", args=[self.open_message.pk]), fetch_redirect_response=False)
        self.assertContains(
            self.client.get(invalid.url),
            "This contact does not have an email address that can receive a reply.",
        )
        self.assertEqual(len(mail.outbox), 0)
        ContactMessage.objects.filter(pk=self.open_message.pk).update(email="ada.writer@example.com")
        with patch("accounts.emails.send_mail", side_effect=Exception("smtp://user:supersecret@mail.internal")):
            failed = self.client.post(url, {"reply": "Hello there"})
        self.assertRedirects(failed, reverse("ops:contact_message", args=[self.open_message.pk]), fetch_redirect_response=False)
        followed = self.client.get(failed.url)
        self.assertContains(followed, "The reply could not be sent. The contact message was not changed.")
        self.assertNotContains(followed, "Reply sent")
        self.assertNotContains(followed, "supersecret")
        self.assertNotContains(followed, "mail.internal")
        self.assertEqual(len(mail.outbox), 0)
        self.open_message.refresh_from_db()
        self.assertFalse(self.open_message.is_resolved)
        self.assertEqual(self.open_message.email, "ada.writer@example.com")
        self.assertTrue(self.open_message.message.startswith("The course reader stops"))

        secure = self.client.__class__(enforce_csrf_checks=True)
        secure.force_login(self.superuser)
        denied = secure.post(url, {"reply": "Hello there"})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)
        self.open_message.refresh_from_db()
        self.assertFalse(self.open_message.is_resolved)

    def test_public_submission_stays_private(self):
        self.client.force_login(self.student)
        public = self.client.get(reverse("pages:contact"))
        self.assertNotContains(public, "The course reader stops")
        empty = self.client.post(reverse("pages:contact"), {"name": "Skip", "email": "", "message": ""})
        self.assertEqual(empty.status_code, 200)
        self.assertFalse(ContactMessage.objects.filter(name="Skip").exists())
        self.client.logout()
        sent = self.client.post(reverse("pages:contact"), {
            "name": "Public Sender",
            "email": "public.sender@example.com",
            "message": "Please add a keyboard shortcut.",
        })
        self.assertRedirects(sent, reverse("pages:contact"))
        stored = ContactMessage.objects.get(email="public.sender@example.com")
        self.assertFalse(stored.is_resolved)
        self.assertNotIn("keyboard shortcut", sent.url)

        self.client.force_login(self.student)
        hidden = self.client.get(reverse("pages:contact"))
        self.assertNotContains(hidden, "Please add a keyboard shortcut.")
        self.assertEqual(self.client.get(reverse("ops:contact")).status_code, 403)

        self.client.force_login(self.superuser)
        inbox = self.client.get(reverse("ops:contact"), {"q": "keyboard shortcut"})
        self.assertContains(inbox, "Public Sender")


class AnalyticsReportTests(TestCase):
    def setUp(self):
        self.ada = User.objects.create_user(
            email="ada.analytics@example.com", password="pass12345", username="ada_analytics", level=4,
        )
        self.ben = User.objects.create_user(
            email="ben.analytics@example.com", password="pass12345", username="ben_analytics",
        )
        self.cara = User.objects.create_user(
            email="cara.analytics@example.com", password="pass12345", username="cara_analytics",
        )
        self.staff = User.objects.create_user(
            email="staff.analytics@example.com", password="pass12345", is_staff=True,
        )
        self.superuser = User.objects.create_superuser(email="analyticsops@example.com", password="pass12345")
        self.alpha = Course.objects.create(code="AN-1", title="Alpha course", short_description="Alpha", is_published=True)
        self.beta = Course.objects.create(code="AN-2", title="Beta course", short_description="Beta", is_published=True)
        CourseProgress.objects.create(user=self.ada, course=self.alpha)
        CourseProgress.objects.create(user=self.staff, course=self.alpha)
        ReadingProgress.objects.create(user=self.ada, course=self.alpha, last_page_index=1)
        self.first = GameAttempt.objects.create(
            user=self.ada, game_key="phishing_simulator", score=2, total_questions=5,
        )
        GameAttempt.objects.create(
            user=self.ada, game_key="phishing_simulator", score=5, total_questions=5,
        )
        self.old = GameAttempt.objects.create(
            user=self.ada, game_key="password_cracker", score=5, total_questions=5,
        )
        GameAttempt.objects.filter(pk=self.old.pk).update(completed_at=timezone.now() - timedelta(days=40))
        GameAttempt.objects.create(
            user=self.staff, game_key="phishing_simulator", score=0, total_questions=5,
        )
        PracticeSession.objects.create(
            user=self.ada, domain="phishing", activity_type="simulation", scenario_key="phish-demo",
            difficulty="beginner", score=80, max_score=100, status="completed", completed_at=timezone.now(),
        )
        PracticeSession.objects.create(
            user=self.ada, domain="phishing", activity_type="incident", scenario_key="phish-open",
            difficulty="beginner", score=10, max_score=100, status="in_progress",
        )
        PracticeSession.objects.create(
            user=self.staff, domain="phishing", activity_type="simulation", scenario_key="staff-demo",
            difficulty="beginner", score=100, max_score=100, status="completed", completed_at=timezone.now(),
        )
        IssuedCertificate.objects.create(
            user=self.ada, certificate_id="CQ-2026-ANALYT01", verification_token="analytics-token-ada",
            recipient_name="Ada", score=90, issued_at=timezone.now(),
            pdf_file=SimpleUploadedFile("ada.pdf", b"%PDF-1.4"),
        )
        IssuedCertificate.objects.create(
            user=self.ben, certificate_id="CQ-2026-ANALYT02", verification_token="analytics-token-ben",
            recipient_name="Ben", score=70, issued_at=timezone.now(),
        )
        badge = Badge.objects.get(code="first_steps")
        UserBadge.objects.create(user=self.ada, badge=badge)
        ContactMessage.objects.create(name="Ada", email="ada.analytics@example.com", message="Need help")
        Notification.objects.create(user=self.ada, message="Analytics notice")
        QuestionSet.objects.create(
            course="phishing_simulator", set_number=1, set_type=QuestionSet.SET_TYPE_NORMAL,
            status=QuestionSet.STATUS_REVIEW,
        )
        UserActivityDay.objects.create(user=self.ada, day=timezone.localdate())
        UserActivityDay.objects.create(user=self.staff, day=timezone.localdate())

    def test_access_is_superuser_only(self):
        url = reverse("ops:analytics")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login/", response.url)
        for user in (self.ada, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url).status_code, 403)

    def test_metrics_match_known_records_and_overview(self):
        from dashboard.ops import overview_kpis

        self.client.force_login(self.superuser)
        before = overview_kpis()
        page = self.client.get(reverse("ops:analytics"))
        report = page.context["report"]
        self.assertEqual(overview_kpis()["completion_rate"], before["completion_rate"])
        self.assertEqual(before["published_courses"], 2)
        self.assertEqual(before["completion_rate"], 17)
        self.assertEqual(before["game_attempts"], 4)
        self.assertEqual(report["completion_rate"], 17)
        self.assertEqual(report["completion_denominator"], 6)
        self.assertEqual(report["completions"], 1)
        self.assertEqual(report["students"], 3)
        self.assertEqual(report["active_in_period"], 1)
        self.assertEqual(report["readers"], 1)
        self.assertEqual(report["busiest_course"]["code"], "AN-1")
        self.assertEqual(report["low_courses"][0]["code"], "AN-2")
        self.assertEqual(report["game_attempts"], 3)
        self.assertEqual(report["mean_game"], 80)
        self.assertEqual(report["first_game"], 70)
        phishing = next(row for row in report["games"] if row["key"] == "phishing_simulator")
        self.assertEqual(phishing["attempts"], 2)
        self.assertEqual(phishing["avg_percent"], 70)
        self.assertEqual(phishing["first_percent"], 40)
        self.assertEqual(phishing["bank"], "Phishing")
        self.assertEqual(report["practice_sessions"], 2)
        self.assertEqual(report["practice_completed"], 1)
        self.assertEqual(report["practice_rate"], 50)
        self.assertEqual(report["mean_practice"], 80)
        incident = next(row for row in report["activities"] if row["activity"] == "Incident")
        self.assertEqual(incident["completed"], 0)
        self.assertIsNone(incident["avg_percent"])
        self.assertEqual(report["certificates"], 1)
        self.assertEqual(report["incomplete_certificates"], 1)
        self.assertEqual(report["badge_students"], 1)
        self.assertEqual(report["open_contact"], 1)
        self.assertEqual(report["unread_notifications"], 1)
        self.assertEqual(report["review_sets"], 1)
        self.assertEqual(sum(bar["n"] for bar in report["signups_chart"]), report["signups"])
        self.assertContains(page, "Alpha course")
        self.assertNotContains(page, self.ada.password)
        self.assertEqual(self.client.post(reverse("ops:analytics")).status_code, 405)
        self.ada.refresh_from_db()
        self.assertEqual(self.ada.level, 4)

    def test_period_filter_excludes_older_attempts(self):
        self.client.force_login(self.superuser)
        week = self.client.get(reverse("ops:analytics"), {"period": "7"})
        report = week.context["report"]
        self.assertEqual(report["period"], "7")
        self.assertEqual(report["game_attempts"], 2)
        self.assertEqual(report["mean_game"], 70)
        self.assertEqual(report["first_game"], 40)
        password = next(row for row in report["games"] if row["key"] == "password_cracker")
        self.assertEqual(password["attempts"], 0)
        self.assertIsNone(password["avg_percent"])
        self.assertEqual(report["completion_rate"], 17)
        ignored = self.client.get(reverse("ops:analytics"), {"period": "forever"})
        self.assertEqual(ignored.context["report"]["period"], "all")
        self.assertEqual(ignored.context["report"]["game_attempts"], 3)

    def test_empty_dataset_does_not_invent_averages(self):
        User.objects.all().delete()
        superuser = User.objects.create_superuser(email="empty.analytics@example.com", password="pass12345")
        self.client.force_login(superuser)
        page = self.client.get(reverse("ops:analytics"))
        report = page.context["report"]
        self.assertEqual(report["students"], 0)
        self.assertIsNone(report["completion_rate"])
        self.assertIsNone(report["mean_game"])
        self.assertIsNone(report["mean_practice"])
        self.assertIsNone(report["practice_rate"])
        self.assertTrue(all(row["attempts"] == 0 for row in report["games"]))
        self.assertContains(page, "—")


class SystemHealthTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(email="health.student@example.com", password="pass12345")
        self.staff = User.objects.create_user(
            email="health.staff@example.com", password="pass12345", is_staff=True,
        )
        self.superuser = User.objects.create_superuser(email="healthops@example.com", password="pass12345")

    def test_access_is_superuser_only(self):
        url = reverse("ops:settings")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login/", response.url)
        for user in (self.student, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url).status_code, 403)

    def test_development_status_hides_secrets_and_does_not_change_settings(self):
        from django.conf import settings

        self.client.force_login(self.superuser)
        debug = settings.DEBUG
        secret = settings.SECRET_KEY
        page = self.client.get(reverse("ops:settings"))
        self.assertContains(page, "Development" if settings.DEBUG else "production flag")
        self.assertContains(page, "Secret values are not shown")
        self.assertContains(page, "No test message was sent")
        self.assertContains(page, "No application version")
        self.assertNotContains(page, settings.SECRET_KEY)
        self.assertNotContains(page, settings.EMAIL_HOST_PASSWORD or "email-password-placeholder")
        self.assertNotContains(page, settings.GEMINI_API_KEY or "gemini-key-placeholder")
        self.assertNotContains(page, settings.GOOGLE_CLIENT_SECRET or "oauth-secret-placeholder")
        self.assertEqual(settings.DEBUG, debug)
        self.assertEqual(settings.SECRET_KEY, secret)
        self.assertEqual(self.client.post(reverse("ops:settings")).status_code, 405)

    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True, SECURE_HSTS_SECONDS=31536000)
    def test_production_flags_are_reported_from_settings(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:settings"), secure=True)
        report = page.content.decode()
        self.assertIn("Debug is off", report)
        self.assertIn("Session and CSRF cookies are marked secure.", report)
        self.assertIn("Enabled.", report)
        self.assertNotIn("Off while Debug is on.", report)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST_USER="",
        EMAIL_HOST_PASSWORD="",
        DEFAULT_FROM_EMAIL="",
        BREVO_API_KEY="",
        GEMINI_API_KEY="",
        PUBLIC_BASE_URL="",
    )
    def test_missing_configuration_is_not_called_healthy(self):
        self.client.force_login(self.superuser)
        page = self.client.get(reverse("ops:settings"))
        self.assertContains(page, "username, password, or from address is missing")
        self.assertContains(page, "Optional AI key is not set")
        self.assertContains(page, "Not set. Certificate links can fall back")
        names = {
            item["name"]: item["status"]
            for group in page.context["groups"]
            for item in group["items"]
        }
        self.assertEqual(names["Email credentials"], "attention")
        self.assertEqual(names["Email delivery"], "unknown")
        self.assertEqual(names["Application version"], "unknown")
        self.assertEqual(names["Logging"], "unknown")

    def test_database_failure_is_attention_without_the_exception_text(self):
        self.client.force_login(self.superuser)
        with patch(
            "dashboard.ops._database_reachable",
            side_effect=Exception("postgres://user:supersecret@db.internal/main"),
        ):
            page = self.client.get(reverse("ops:settings"))
        self.assertContains(page, "A connection could not be opened.")
        self.assertNotContains(page, "supersecret")
        self.assertNotContains(page, "db.internal")
        self.assertContains(page, "Not checked because the database connection failed")
        names = {
            item["name"]: item["status"]
            for group in page.context["groups"]
            for item in group["items"]
        }
        self.assertEqual(names["Database connectivity"], "attention")
        self.assertEqual(names["Pending migrations"], "unknown")

    def test_deployment_findings_are_redacted(self):
        from django.conf import settings
        from django.core.checks import Warning as CheckWarning

        self.client.force_login(self.superuser)
        leaked = CheckWarning(
            f"Token {settings.SECRET_KEY} and postgres://user:supersecret@db/main",
            id="security.W999",
        )
        with patch.dict(os.environ, {"DATABASE_URL": "postgres://user:supersecret@db/main"}, clear=False):
            with patch("django.core.checks.run_checks", return_value=[leaked]):
                page = self.client.get(reverse("ops:settings"))
        self.assertNotContains(page, settings.SECRET_KEY)
        self.assertNotContains(page, "supersecret")
        self.assertContains(page, "[redacted]")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    BREVO_API_KEY="",
)
class AdministratorAndStatusEmailTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email="status.student@example.com", password="pass12345", username="statusstudent",
        )
        self.staff = User.objects.create_user(
            email="status.staff@example.com", password="pass12345", is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            email="status.ops@example.com", password="pass12345", username="statusops",
        )

    def test_only_superusers_can_create_administrators(self):
        url = reverse("ops:create_administrator")
        self.assertEqual(self.client.get(url).status_code, 302)
        for user in (self.student, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {
                "email": "new.admin@example.com",
                "username": "newadmin",
                "password": "AdminQuest-2026-key",
                "confirm": "AdminQuest-2026-key",
                "is_superuser": "1",
            }).status_code, 403)
        self.assertFalse(User.objects.filter(email="new.admin@example.com").exists())

        self.client.force_login(self.superuser)
        created = self.client.post(url, {
            "email": "new.admin@example.com",
            "username": "newadmin",
            "password": "AdminQuest-2026-key",
            "confirm": "AdminQuest-2026-key",
            "is_superuser": "0",
            "is_staff": "0",
        })
        self.assertRedirects(created, url)
        admin = User.objects.get(email="new.admin@example.com")
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.check_password("AdminQuest-2026-key"))

        duplicate = self.client.post(url, {
            "email": "new.admin@example.com",
            "username": "anothername",
            "password": "AdminQuest-2026-key",
            "confirm": "AdminQuest-2026-key",
        })
        self.assertEqual(duplicate.status_code, 200)
        self.assertContains(duplicate, "already exists")
        secure = self.client.__class__(enforce_csrf_checks=True)
        secure.force_login(self.superuser)
        self.assertEqual(secure.post(url, {
            "email": "csrf.admin@example.com",
            "username": "csrfadmin",
            "password": "AdminQuest-2026-key",
            "confirm": "AdminQuest-2026-key",
        }).status_code, 403)

    @override_settings(DEFAULT_FROM_EMAIL="ops@example.com")
    def test_status_change_emails_only_after_a_real_change(self):
        self.client.force_login(self.superuser)
        url = reverse("ops:student_status", args=[self.student.pk])
        first = self.client.post(url, {"action": "deactivate"})
        self.assertRedirects(first, reverse("ops:student", args=[self.student.pk]), fetch_redirect_response=False)
        page = self.client.get(first.url)
        self.assertContains(page, "A suspension email was sent.")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.student.email])
        self.assertIn("suspended", mail.outbox[0].subject.lower())
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)

        again = self.client.post(url, {"action": "deactivate"})
        self.assertRedirects(again, reverse("ops:student", args=[self.student.pk]), fetch_redirect_response=False)
        self.assertContains(self.client.get(again.url), "already inactive")
        self.assertEqual(len(mail.outbox), 1)

        with patch("accounts.emails.send_mail", side_effect=Exception("smtp://user:supersecret@mail")):
            restored = self.client.post(url, {"action": "activate"})
        self.assertRedirects(restored, reverse("ops:student", args=[self.student.pk]), fetch_redirect_response=False)
        followed = self.client.get(restored.url)
        self.assertContains(followed, "can sign in again")
        self.assertContains(followed, "could not be sent")
        self.assertNotContains(followed, "supersecret")
        self.student.refresh_from_db()
        self.assertTrue(self.student.is_active)
        self.assertEqual(len(mail.outbox), 1)
