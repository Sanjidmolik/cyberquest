"""Admin mission-attempt review: access control, outcome mapping, filters, pagination, query cost."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from dashboard.mission_attempts import PAGE_SIZE
from games.models import GameAttempt

User = get_user_model()
URL = reverse("ops:mission_attempts")


def _attempt(user, game="phishing_simulator", *, status="completed", score=4, total=5,
             elapsed=30, method="manual", started=None, deadline=None, xp=40):
    now = timezone.now()
    started = started or now - timedelta(minutes=5)
    return GameAttempt.objects.create(
        user=user, game_key=game, status=status, score=score, total_questions=total,
        elapsed_seconds=elapsed if status != "in_progress" else None,
        submission_method=method if status != "in_progress" else "",
        started_at=started, deadline_at=deadline or started + timedelta(seconds=60),
        completed_at=None if status == "in_progress" else started + timedelta(seconds=elapsed or 0),
        xp_awarded=xp if status != "in_progress" else 0,
    )


class AccessTests(TestCase):
    def test_only_superusers_can_open_the_page(self):
        self.assertEqual(self.client.get(URL).status_code, 302)
        student = User.objects.create_user(email="s@example.com", password="x")
        self.client.force_login(student)
        self.assertEqual(self.client.get(URL).status_code, 403)
        staff = User.objects.create_user(email="staff@example.com", password="x", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(URL).status_code, 403)


class AttemptReviewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="root@example.com", password="x")
        self.client.force_login(self.admin)
        self.ana = User.objects.create_user(email="ana@example.com", password="x", username="ana", full_name="Ana Li")
        self.ben = User.objects.create_user(email="ben@example.com", password="x", username="ben")
        now = timezone.now()
        self.completed = _attempt(self.ana, score=5, elapsed=20)
        self.timed_out = _attempt(self.ana, "cryptography", status="timed_out", score=2, elapsed=60, method="timeout")
        self.abandoned = _attempt(self.ben, status="timed_out", score=0, elapsed=60, method="expiry", xp=0)
        self.active = _attempt(self.ben, "network_defense", status="in_progress", started=now - timedelta(seconds=10))
        self.stale = _attempt(
            self.ben, "steganography", status="in_progress",
            started=now - timedelta(minutes=10), deadline=now - timedelta(minutes=9),
        )

    def _ids(self, **params):
        response = self.client.get(URL, params)
        self.assertEqual(response.status_code, 200)
        return {row["id"] for row in response.context["report"]["rows"]}, response

    def test_outcomes_follow_the_stored_data(self):
        self.assertEqual(self._ids(outcome="completed")[0], {self.completed.pk})
        self.assertEqual(self._ids(outcome="timed_out")[0], {self.timed_out.pk})
        self.assertEqual(self._ids(outcome="abandoned")[0], {self.abandoned.pk, self.stale.pk})
        self.assertEqual(self._ids(outcome="active")[0], {self.active.pk})
        summary = self._ids()[1].context["report"]["summary"]
        self.assertEqual(
            (summary["total"], summary["completed"], summary["timed_out"], summary["abandoned"], summary["active"]),
            (5, 1, 1, 2, 1),
        )

    def test_unfinished_attempts_show_no_score_or_completion(self):
        _ids, response = self._ids(outcome="active")
        row = response.context["report"]["rows"][0]
        self.assertIsNone(row["score"])
        self.assertIsNone(row["completed_at"])
        self.assertIsNone(row["accuracy"])

    def test_viewing_does_not_close_expired_attempts(self):
        self._ids()
        self.stale.refresh_from_db()
        self.assertEqual(self.stale.status, GameAttempt.STATUS_IN_PROGRESS)

    def test_search_by_name_email_username_and_id(self):
        self.assertEqual(self._ids(q="Ana Li")[0], {self.completed.pk, self.timed_out.pk})
        self.assertEqual(self._ids(q="ben@example")[0], {self.abandoned.pk, self.active.pk, self.stale.pk})
        self.assertEqual(self._ids(q=str(self.abandoned.pk))[0] >= {self.abandoned.pk}, True)

    def test_mission_accuracy_and_duration_filters(self):
        self.assertEqual(self._ids(mission="cryptography")[0], {self.timed_out.pk})
        self.assertEqual(self._ids(min_accuracy="80")[0], {self.completed.pk})
        self.assertEqual(self._ids(max_accuracy="40", outcome="timed_out")[0], {self.timed_out.pk})
        self.assertEqual(self._ids(max_seconds="25")[0], {self.completed.pk})
        self.assertEqual(self._ids(min_seconds="50", max_seconds="60")[0], {self.timed_out.pk, self.abandoned.pk})

    def test_date_range_filter(self):
        old = _attempt(self.ana, "password_cracker", started=timezone.now() - timedelta(days=40))
        today = timezone.localdate().isoformat()
        ids, _ = self._ids(start=today, end=today)
        self.assertNotIn(old.pk, ids)
        ids, _ = self._ids(end=(timezone.localdate() - timedelta(days=30)).isoformat())
        self.assertEqual(ids, {old.pk})

    def test_invalid_filters_are_ignored(self):
        ids, _ = self._ids(mission="osint'; DROP", min_accuracy="abc", start="2026-99-99", sort="password")
        self.assertEqual(len(ids), 5)

    def test_staff_attempts_are_hidden_unless_requested(self):
        mine = _attempt(self.admin)
        self.assertNotIn(mine.pk, self._ids()[0])
        self.assertIn(mine.pk, self._ids(include_staff="1")[0])

    def test_sort_by_fastest(self):
        _ids, response = self._ids(sort="fastest", outcome="completed")
        rows = response.context["report"]["rows"]
        self.assertEqual(rows[0]["id"], self.completed.pk)

    def test_email_is_shown_to_superusers(self):
        self.assertContains(self.client.get(URL), "ana@example.com")


class PaginationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="root@example.com", password="x")
        self.client.force_login(self.admin)
        self.learner = User.objects.create_user(email="many@example.com", password="x", username="many")

    def _make(self, count):
        for i in range(count):
            _attempt(self.learner, elapsed=10 + i)

    def test_pages_and_filters_survive_page_links(self):
        self._make(PAGE_SIZE + 5)
        first = self.client.get(URL, {"mission": "phishing_simulator", "sort": "fastest"})
        self.assertEqual(len(first.context["report"]["rows"]), PAGE_SIZE)
        self.assertContains(first, "mission=phishing_simulator&amp;sort=fastest&amp;page=2")
        second = self.client.get(URL, {"mission": "phishing_simulator", "sort": "fastest", "page": 2})
        self.assertEqual(len(second.context["report"]["rows"]), 5)

    def test_query_count_does_not_grow_with_rows(self):
        self._make(3)
        with CaptureQueriesContext(connection) as small:
            self.client.get(URL)
        self._make(PAGE_SIZE)
        with CaptureQueriesContext(connection) as large:
            self.client.get(URL)
        self.assertEqual(len(small), len(large))
