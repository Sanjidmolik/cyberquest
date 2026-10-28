"""The site's calendar is Dhaka time (UTC+6): days and leaderboard weeks turn over at local
midnight, not at UTC midnight. 23:59 and 00:01 Dhaka time are the same UTC day."""

from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserActivityDay
from games.models import GameAttempt
from leaderboard import ranking

User = get_user_model()
DHAKA = ZoneInfo("Asia/Dhaka")


def dhaka(*args):
    return datetime(*args, tzinfo=DHAKA)


class SiteCalendarTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_site_time_zone_is_dhaka_and_storage_stays_utc(self):
        self.assertEqual(settings.TIME_ZONE, "Asia/Dhaka")
        self.assertTrue(settings.USE_TZ)
        late, early = dhaka(2026, 10, 28, 23, 59), dhaka(2026, 10, 29, 0, 1)
        self.assertEqual(late.astimezone(ZoneInfo("UTC")).date(), early.astimezone(ZoneInfo("UTC")).date())

    def test_streak_counts_23_59_and_00_01_as_two_days(self):
        user = User.objects.create_user(email="streak@example.com", password="testpass123", username="streaky")
        for moment in (dhaka(2026, 10, 28, 23, 59), dhaka(2026, 10, 29, 0, 1)):
            with mock.patch("django.utils.timezone.now", return_value=moment):
                user.record_daily_activity()
        user.refresh_from_db()
        self.assertEqual((user.current_streak, user.longest_streak), (2, 2))
        self.assertEqual(user.last_active_date.isoformat(), "2026-10-29")
        self.assertEqual(sorted(d.isoformat() for d in UserActivityDay.objects.filter(user=user)
                                .values_list("day", flat=True)), ["2026-10-28", "2026-10-29"])

    def test_same_local_day_counts_once(self):
        user = User.objects.create_user(email="once@example.com", password="testpass123", username="once")
        for moment in (dhaka(2026, 10, 29, 0, 1), dhaka(2026, 10, 29, 23, 59)):
            with mock.patch("django.utils.timezone.now", return_value=moment):
                user.record_daily_activity()
        user.refresh_from_db()
        self.assertEqual(user.current_streak, 1)
        self.assertEqual(UserActivityDay.objects.filter(user=user).count(), 1)

    def test_leaderboard_week_turns_over_at_saturday_00_00_dhaka(self):
        friday_late, saturday_early = dhaka(2026, 10, 30, 23, 59), dhaka(2026, 10, 31, 0, 1)
        old_week = User.objects.create_user(email="fri@example.com", password="testpass123", username="friday")
        new_week = User.objects.create_user(email="sat@example.com", password="testpass123", username="saturday")
        for user, when in ((old_week, friday_late), (new_week, saturday_early)):
            GameAttempt.objects.create(user=user, game_key="phishing", score=5, total_questions=5, xp_awarded=20,
                                       completed_at=when, status="completed")
        now = dhaka(2026, 10, 31, 0, 5)
        start, end = ranking.period_bounds("week", now)
        self.assertEqual(start, dhaka(2026, 10, 31, 0, 0))
        self.assertEqual(ranking.period_label("week", now), "This week: 31 Oct – 6 Nov")
        self.assertEqual([u.username for u in ranking.ranked("week", now)], ["saturday"])
        last_week = dhaka(2026, 10, 30, 23, 59, 30)
        self.assertEqual([u.username for u in ranking.ranked("week", last_week)], ["friday"])
        self.client.force_login(new_week)
        with mock.patch("django.utils.timezone.now", return_value=now):
            page = self.client.get(reverse("leaderboard:list"), {"period": "week"})
        self.assertEqual([r["username"] for r in page.context["podium"]], ["saturday"])

    def test_month_turns_over_at_local_midnight(self):
        self.assertEqual(ranking.period_bounds("month", dhaka(2026, 11, 1, 0, 1))[0], dhaka(2026, 11, 1, 0, 0))
        self.assertEqual(ranking.period_bounds("month", dhaka(2026, 10, 31, 23, 59))[0], dhaka(2026, 10, 1, 0, 0))

    def test_age_check_uses_the_local_date(self):
        from datetime import date

        from django.core.exceptions import ValidationError

        from accounts.validators import validate_minimum_age
        birthday = date(2013, 10, 29)                          # 13 on 29 Oct 2026 (Dhaka)
        with mock.patch("django.utils.timezone.now", return_value=dhaka(2026, 10, 29, 0, 30)):
            validate_minimum_age(birthday)                   # 28 Oct 18:30 UTC: still the 29th here
        with mock.patch("django.utils.timezone.now", return_value=dhaka(2026, 10, 28, 23, 30)):
            with self.assertRaises(ValidationError):
                validate_minimum_age(birthday)
