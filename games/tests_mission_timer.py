from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from games.attempts import clock_label
from games.models import GameAttempt

User = get_user_model()


class MissionTimerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="timer@example.com", password="pass12345", username="timeruser",
        )
        self.client.login(email="timer@example.com", password="pass12345")
        self.url = reverse("games:online_safety")
        self.patcher = patch("games.views.is_game_unlocked", return_value=True)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def _start(self):
        response = self.client.post(self.url, {"action": "start"})
        self.assertEqual(response.status_code, 302)
        play = self.client.get(self.url)
        self.assertEqual(play.status_code, 200)
        self.assertEqual(play.context["phase"], "play")
        return play

    def test_intro_does_not_start_the_clock(self):
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["phase"], "intro")
        self.assertFalse(GameAttempt.objects.filter(user=self.user).exists())
        self.assertContains(page, "Begin mission")
        self.assertNotContains(page, "mission-timer.js")

    def test_start_sets_a_sixty_second_deadline_and_refresh_reuses_it(self):
        self._start()
        attempt = GameAttempt.objects.get(user=self.user, game_key="online_safety")
        self.assertEqual(attempt.status, GameAttempt.STATUS_IN_PROGRESS)
        delta = (attempt.deadline_at - attempt.started_at).total_seconds()
        self.assertEqual(int(delta), 60)
        deadline = attempt.deadline_at
        self.client.post(self.url, {"action": "start"})
        self.client.get(self.url)
        attempt.refresh_from_db()
        self.assertEqual(attempt.deadline_at, deadline)
        self.assertEqual(GameAttempt.objects.filter(user=self.user).count(), 1)

    def test_early_correct_submission_is_graded_once(self):
        play = self._start()
        questions = play.context["questions"]
        post = {f"question_{q['id']}": str(q["correct_index"]) for q in questions}
        post["action"] = "submit"
        result = self.client.post(self.url, post)
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Correct")
        self.assertContains(result, "Answer Review")
        self.assertContains(result, "Return to Missions")
        self.assertContains(result, "Try Again")
        self.assertContains(result, "XP earned")
        self.assertContains(result, f"{len(questions)} / {len(questions)}")
        attempt = GameAttempt.objects.get(user=self.user)
        self.assertEqual(attempt.status, GameAttempt.STATUS_COMPLETED)
        self.assertEqual(attempt.score, len(questions))
        self.assertEqual(attempt.xp_awarded, attempt.score * 20)
        self.assertLess(attempt.elapsed_seconds, 60)
        self.user.refresh_from_db()
        xp = self.user.xp
        again = self.client.post(self.url, post)
        self.assertEqual(again.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.xp, xp)
        self.assertEqual(GameAttempt.objects.filter(user=self.user, status=GameAttempt.STATUS_COMPLETED).count(), 1)

    def test_expired_attempt_marks_unanswered_incorrect_and_ignores_a_late_restart(self):
        self._start()
        attempt = GameAttempt.objects.get(user=self.user)
        attempt.deadline_at = timezone.now() - timedelta(seconds=5)
        attempt.save(update_fields=["deadline_at"])
        page = self.client.get(self.url)
        self.assertContains(page, "Time&#x27;s up")
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, GameAttempt.STATUS_TIMED_OUT)
        self.assertEqual(attempt.score, 0)
        self.assertEqual(attempt.elapsed_seconds, 60)
        self.assertEqual(attempt.time_remaining_seconds, 0)

    def test_client_deadline_cannot_extend_the_attempt(self):
        play = self._start()
        attempt = GameAttempt.objects.get(user=self.user)
        attempt.deadline_at = timezone.now() - timedelta(seconds=2)
        attempt.save(update_fields=["deadline_at"])
        questions = play.context["questions"]
        post = {f"question_{q['id']}": str(q["correct_index"]) for q in questions}
        post["action"] = "submit"
        post["deadline"] = (timezone.now() + timedelta(hours=1)).isoformat()
        self.client.post(self.url, post)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, GameAttempt.STATUS_TIMED_OUT)
        self.assertEqual(attempt.score, len(questions))
        self.assertEqual(attempt.elapsed_seconds, 60)

    def test_clock_label_matches_the_countdown_readout(self):
        self.assertEqual(clock_label(60000), "01:00")
        self.assertEqual(clock_label(47000), "00:47")
        self.assertEqual(clock_label(15000), "00:15")
        self.assertEqual(clock_label(5000), "00:05")
        self.assertEqual(clock_label(0), "00:00")

    def test_refresh_exposes_the_same_remaining_time(self):
        self._start()
        attempt = GameAttempt.objects.get(user=self.user)
        attempt.deadline_at = timezone.now() + timedelta(seconds=47)
        attempt.save(update_fields=["deadline_at"])
        page = self.client.get(self.url)
        self.assertContains(page, "mission-timer.js")
        self.assertContains(page, "00:47")
        sync = self.client.get(self.url + "?sync=1", HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(sync.status_code, 200)
        self.assertTrue(sync.json()["running"])
        self.assertGreater(sync.json()["remaining_ms"], 40000)
        self.assertLess(sync.json()["remaining_ms"], 48000)

    def test_saving_an_answer_does_not_finish_the_attempt(self):
        play = self._start()
        question = play.context["questions"][0]
        response = self.client.post(
            self.url,
            {"action": "save", f"question_{question['id']}": "0"},
            HTTP_X_REQUESTED_WITH="fetch",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        attempt = GameAttempt.objects.get(user=self.user)
        self.assertEqual(attempt.status, GameAttempt.STATUS_IN_PROGRESS)
        self.assertEqual(attempt.answers[str(question["id"])], 0)

    def test_reopening_keeps_the_original_deadline(self):
        self._start()
        attempt = GameAttempt.objects.get(user=self.user)
        frozen = timezone.now() + timedelta(seconds=45)
        attempt.started_at = frozen - timedelta(seconds=60)
        attempt.deadline_at = frozen
        attempt.save(update_fields=["started_at", "deadline_at"])
        page = self.client.get(self.url)
        self.assertContains(page, "00:45")
        self.assertContains(page, "data-deadline=")
        self.assertEqual(page["Cache-Control"], "no-store, max-age=0")
        self.client.post(self.url, {"action": "start"})
        again = self.client.get(self.url)
        self.assertEqual(again.context["attempt"].pk, attempt.pk)
        attempt.refresh_from_db()
        self.assertEqual(attempt.deadline_at, frozen)
        self.assertEqual(attempt.status, GameAttempt.STATUS_IN_PROGRESS)
        self.assertEqual(GameAttempt.objects.filter(user=self.user).count(), 1)

    def test_repeat_attempt_does_not_award_xp_again(self):
        play = self._start()
        questions = play.context["questions"]
        post = {f"question_{q['id']}": str(q["correct_index"]) for q in questions}
        post["action"] = "submit"
        self.client.post(self.url, post)
        self.user.refresh_from_db()
        xp = self.user.xp
        self.assertGreater(xp, 0)
        self.client.post(self.url, {"action": "start"})
        replay = self.client.get(self.url)
        self.assertEqual(replay.context["phase"], "play")
        again = self.client.post(self.url, post)
        self.assertContains(again, "No new XP")
        self.assertContains(again, "ALREADY FINISHED")
        self.user.refresh_from_db()
        self.assertEqual(self.user.xp, xp)
        self.assertEqual(
            GameAttempt.objects.filter(user=self.user, xp_awarded__gt=0).count(),
            1,
        )

    def test_osint_stays_unavailable(self):
        response = self.client.get(reverse("games:osint"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(GameAttempt.objects.filter(game_key="osint").exists())
