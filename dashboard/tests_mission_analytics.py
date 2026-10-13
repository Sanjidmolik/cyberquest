from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from games.models import GameAttempt

User = get_user_model()


class MissionAnalyticsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="ops-time@example.com", password="pass12345")
        self.student = User.objects.create_user(
            email="fast@example.com", password="pass12345", username="fastlearner", full_name="Fast Learner",
        )
        self.other = User.objects.create_user(
            email="slow@example.com", password="pass12345", username="slowlearner", full_name="Slow Learner",
        )
        now = timezone.now()
        self._attempt(self.student, "phishing_simulator", 4, 12, now)
        self._attempt(self.student, "phishing_simulator", 2, 8, now - timedelta(minutes=5))
        self._attempt(self.other, "password_cracker", 5, 40, now - timedelta(minutes=10))
        self._attempt(self.other, "network_defense", 1, None, now - timedelta(days=1), status=GameAttempt.STATUS_TIMED_OUT)
        GameAttempt.objects.create(
            user=self.student, game_key="cryptography", score=4, total_questions=5, xp_awarded=0,
        )

    def _attempt(self, user, game, score, elapsed, when, status=GameAttempt.STATUS_COMPLETED):
        attempt = GameAttempt.objects.create(
            user=user,
            game_key=game,
            score=score,
            total_questions=5,
            status=status,
            started_at=when - timedelta(seconds=elapsed or 60),
            deadline_at=when,
            elapsed_seconds=elapsed,
            time_remaining_seconds=0 if elapsed is None else max(0, 60 - elapsed),
            submission_method="manual" if status == GameAttempt.STATUS_COMPLETED else "timeout",
        )
        GameAttempt.objects.filter(pk=attempt.pk).update(completed_at=when)
        return attempt

    def test_students_cannot_open_mission_analytics(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("ops:mission_analytics"))
        self.assertEqual(response.status_code, 403)

    def test_summary_leaderboard_and_charts_match_records(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:mission_analytics"))
        self.assertEqual(response.status_code, 200)
        report = response.context["report"]
        self.assertEqual(report["summary"]["completed"], 4)
        self.assertEqual(report["summary"]["timed_out"], 1)
        self.assertEqual(report["summary"]["learners"], 2)
        self.assertEqual(report["summary"]["average_time"], 20)
        self.assertEqual(report["summary"]["historical_without_time"], 1)
        learners = [row["learner"] for row in report["leaderboard"]]
        self.assertEqual(learners, ["fastlearner", "slowlearner"])
        self.assertEqual(report["leaderboard"][0]["seconds"], 12)
        self.assertEqual(report["fastest"]["learner"], "fastlearner")
        self.assertEqual(report["highest"]["learner"], "slowlearner")
        self.assertEqual(report["highest"]["seconds"], 40)
        phishing = next(row for row in report["charts"]["by_mission"] if row["key"] == "phishing_simulator")
        self.assertEqual(phishing["avg_time"], 10)
        self.assertContains(response, "fastlearner")

    def test_best_view_keeps_one_row_per_learner(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:mission_analytics"), {"view": "best"})
        learners = [row["learner"] for row in response.context["report"]["leaderboard"]]
        self.assertEqual(learners.count("fastlearner"), 1)
        self.assertEqual(len(learners), 2)

    def test_empty_filter_is_safe(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("ops:mission_analytics"), {
            "mission": "steganography",
            "start": "2000-01-01",
            "end": "2000-01-02",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["report"]["summary"]["completed"], 0)
        self.assertContains(response, "No attempts match")
