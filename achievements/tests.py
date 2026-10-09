from django.contrib.auth import get_user_model
from django.test import TestCase

from achievements.checks import check_and_award_badges
from achievements.models import Badge, UserBadge
from courses.models import Course, CourseProgress
from games.models import GameAttempt
from practice.models import PracticeSession

User = get_user_model()


class AchievementCatalogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="badge.student@gmail.com", password="pass12345", username="badgelearner",
            ethical_agreement=True,
        )

    def _award(self, code):
        before = self.user.xp
        earned = check_and_award_badges(self.user)
        self.user.refresh_from_db()
        self.assertEqual(self.user.xp, before)
        self.assertIn(code, [badge.code for badge in earned])
        again = check_and_award_badges(self.user)
        self.assertNotIn(code, [badge.code for badge in again])
        self.assertEqual(UserBadge.objects.filter(user=self.user, badge__code=code).count(), 1)

    def test_new_conditions_award_once(self):
        course = Course.objects.create(code="MOD-B", title="Badge course", content="Hello", order=1, is_published=True)
        self.assertEqual(check_and_award_badges(self.user), [])
        CourseProgress.objects.create(user=self.user, course=course)
        self._award("first_lesson")

        PracticeSession.objects.create(
            user=self.user, domain="phishing", activity_type="simulation",
            scenario_key="phish-1", difficulty="beginner", status="completed", score=80, max_score=100,
        )
        self._award("phishing_practice")
        PracticeSession.objects.create(
            user=self.user, domain="password", activity_type="simulation",
            scenario_key="pw-1", difficulty="beginner", status="completed", score=70, max_score=100,
        )
        self._award("password_practice")
        PracticeSession.objects.create(
            user=self.user, domain="network", activity_type="simulation",
            scenario_key="net-1", difficulty="beginner", status="completed", score=70, max_score=100,
        )
        earned = [badge.code for badge in check_and_award_badges(self.user)]
        self.assertIn("network_practice", earned)
        self.assertIn("steady_practice", earned)
        self.assertEqual(UserBadge.objects.filter(user=self.user, badge__code="steady_practice").count(), 1)
        self.assertNotIn("steady_practice", [badge.code for badge in check_and_award_badges(self.user)])
        PracticeSession.objects.create(
            user=self.user, domain="cryptography", activity_type="simulation",
            scenario_key="cry-1", difficulty="beginner", status="completed", score=70, max_score=100,
        )
        self._award("crypto_practice")
        PracticeSession.objects.create(
            user=self.user, domain="osint", activity_type="simulation",
            scenario_key="os-1", difficulty="beginner", status="completed", score=70, max_score=100,
        )
        self._award("osint_practice")

        for number in range(10):
            GameAttempt.objects.create(
                user=self.user, game_key="phishing_simulator", score=1, total_questions=5, xp_awarded=0,
            )
        earned = [badge.code for badge in check_and_award_badges(self.user)]
        self.assertIn("ten_games", earned)
        self.assertIn("first_steps", earned)
        self.assertEqual(UserBadge.objects.filter(user=self.user, badge__code="ten_games").count(), 1)
        self.assertEqual(check_and_award_badges(self.user), [])

        GameAttempt.objects.create(
            user=self.user, game_key="cryptography", score=5, total_questions=5, xp_awarded=0,
        )
        self._award("crypto_cracker")
        self.assertTrue(Badge.objects.filter(code="network_guardian", is_active=True).exists())
        self.assertFalse(UserBadge.objects.filter(user=self.user, badge__code="network_guardian").exists())
