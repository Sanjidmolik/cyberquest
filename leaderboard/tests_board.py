"""The full leaderboard page: ordering, ties, periods (Saturday weeks), pagination, own rank,
public fields only, exclusions and query cost."""

from datetime import datetime, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from courses.models import Course, CourseProgress
from games.models import GameAttempt
from leaderboard import ranking
from practice.models import Attempt, Scenario

User = get_user_model()
NOW = timezone.make_aware(datetime(2026, 10, 28, 12, 0))      # a Wednesday


def player(name, xp=0, **extra):
    user = User.objects.create_user(email=f"{name}@example.com", password="testpass123", username=name,
                                    full_name=f"{name.title()} Private-Name", **extra)
    if xp:
        User.objects.filter(pk=user.pk).update(xp=xp)
        user.refresh_from_db()
    return user


def grant(user, xp, when):
    """One mission that awarded `xp` at `when`, and the user's total XP to match."""
    GameAttempt.objects.create(user=user, game_key="phishing", score=5, total_questions=5,
                               xp_awarded=xp, completed_at=when, status="completed")
    User.objects.filter(pk=user.pk).update(xp=user.xp + xp)
    user.refresh_from_db()


class BoardTestCase(TestCase):
    def setUp(self):
        cache.clear()

    def page(self, user, **params):
        self.client.force_login(user)
        with mock.patch("django.utils.timezone.now", return_value=NOW):
            return self.client.get(reverse("leaderboard:list"), params)

    @staticmethod
    def names(response):
        return [row["username"] for row in response.context["podium"] + response.context["rows"]]

    @staticmethod
    def ranks(response):
        return [row["rank"] for row in response.context["podium"] + response.context["rows"]]


class OrderingTests(BoardTestCase):
    def test_ties_share_a_rank_and_whoever_reached_it_first_is_listed_first(self):
        top = player("top")
        late, early, third = player("late"), player("early"), player("third")
        grant(top, 300, NOW - timedelta(days=40))
        grant(late, 200, NOW - timedelta(days=2))
        grant(early, 200, NOW - timedelta(days=9))
        grant(third, 100, NOW - timedelta(days=1))
        res = self.page(top)
        self.assertEqual(self.names(res), ["top", "early", "late", "third"])
        self.assertEqual(self.ranks(res), [1, 2, 2, 4])
        self.assertEqual(self.page(late).context["my_rank"], 2)
        self.assertEqual(self.page(third).context["my_rank"], 4)

    def test_only_staff_and_superusers_are_left_out(self):
        player("student", xp=10)
        editor = player("editor", xp=20)
        editor.groups.add(Group.objects.get(name="Content Editor"))
        player("coach", xp=999, is_staff=True)
        User.objects.create_superuser(email="root@example.com", password="testpass123", username="root")
        player("gone", xp=500, is_active=False)
        User.objects.create_user(email="nameless@example.com", password="testpass123", username="")
        res = self.page(editor)
        self.assertEqual(self.names(res), ["editor", "student"])
        staff = User.objects.get(username="coach")
        staff_view = self.page(staff)
        self.assertIsNone(staff_view.context["my_rank"])
        self.assertContains(staff_view, "Staff accounts aren’t ranked")


class PeriodTests(BoardTestCase):
    def test_weeks_start_on_saturday_in_the_site_time_zone(self):
        start, end = ranking.period_bounds("week", NOW)
        self.assertEqual((timezone.localtime(start).date().isoformat(), timezone.localtime(end).date().isoformat()),
                         ("2026-10-24", "2026-10-31"))
        self.assertEqual(timezone.localtime(start).weekday(), 5)
        self.assertEqual(ranking.period_label("week", NOW), "This week: 24–30 Oct")
        saturday = timezone.make_aware(datetime(2026, 10, 31, 0, 0))
        self.assertEqual(ranking.period_bounds("week", saturday)[0], saturday)
        across = timezone.make_aware(datetime(2026, 11, 2, 9, 0))
        self.assertEqual(ranking.period_label("week", across), "This week: 31 Oct – 6 Nov")
        self.assertEqual(ranking.period_label("month", NOW), "This month: Oct 2026")

    def test_week_and_month_count_only_xp_earned_in_them(self):
        steady, burst, idle = player("steady"), player("burst"), player("idle")
        grant(steady, 500, NOW - timedelta(days=60))          # before this month
        grant(steady, 30, NOW - timedelta(days=1))            # this week
        grant(burst, 80, NOW - timedelta(days=10))            # this month, last week
        grant(idle, 900, NOW - timedelta(days=90))
        Course.objects.create(code="LB-1", title="One", order=1, is_published=True)
        CourseProgress.objects.create(user=steady, course=Course.objects.get(code="LB-1"))

        week = self.page(steady, period="week")
        self.assertEqual(self.names(week), ["steady"])
        self.assertEqual(week.context["podium"][0]["xp"], 30)
        self.assertEqual(week.context["podium"][0]["courses"], 1)
        self.assertContains(week, "This week: 24–30 Oct")
        month = self.page(steady, period="month")
        self.assertEqual(self.names(month), ["burst", "steady"])
        self.assertEqual([r["xp"] for r in month.context["podium"]], [80, 30])
        self.assertEqual(self.names(self.page(steady)), ["idle", "steady", "burst"])
        nothing = self.page(idle, period="week")
        self.assertIsNone(nothing.context["my_rank"])
        self.assertContains(nothing, "haven’t earned XP this week")

    def test_preview_runs_never_count(self):
        from practice.testing import convert_all
        convert_all()
        user = player("previewer")
        Attempt.objects.create(user=user, scenario=Scenario.objects.first(), is_preview=True,
                               finished_at=NOW - timedelta(hours=1), xp_awarded=50)
        for period in ranking.PERIODS[1:]:
            self.assertEqual(self.names(self.page(user, period=period)), [], period)

    def test_unknown_period_falls_back_to_all_time(self):
        player("someone", xp=5)
        self.assertEqual(self.page(User.objects.get(username="someone"), period="year").context["period"], "all")


class PaginationAndOwnRankTests(BoardTestCase):
    def setUp(self):
        super().setUp()
        self.players = [player(f"p{i:02d}", xp=1000 - i) for i in range(31)]   # 3 on the podium + 28

    def test_pages_of_25_after_the_podium(self):
        first = self.page(self.players[0])
        self.assertEqual(len(first.context["podium"]), 3)
        self.assertEqual(len(first.context["rows"]), 25)
        self.assertEqual(first.context["rows"][0]["rank"], 4)
        self.assertEqual(first.context["board"]["pages"], 2)
        second = self.page(self.players[0], page=2)
        self.assertEqual([r["rank"] for r in second.context["rows"]], [29, 30, 31])
        self.assertEqual(self.page(self.players[0], page=99).context["board"]["page"], 2)
        self.assertEqual(self.page(self.players[0], page="x").context["board"]["page"], 1)

    def test_own_rank_is_shown_even_when_off_the_page(self):
        last = self.players[-1]
        res = self.page(last)
        self.assertNotIn("p30", self.names(res))
        self.assertEqual(res.context["me"]["rank"], 31)
        self.assertContains(res, "#31")

    def test_query_count_does_not_grow_with_players(self):
        self.client.force_login(self.players[0])
        cache.clear()
        with CaptureQueriesContext(connection) as small:
            self.client.get(reverse("leaderboard:list"))
        for i in range(40):
            player(f"extra{i}", xp=i)
        cache.clear()
        with CaptureQueriesContext(connection) as large:
            self.client.get(reverse("leaderboard:list"))
        self.assertEqual(len(small), len(large))

    def test_the_board_is_cached_for_a_minute(self):
        self.page(self.players[0])
        player("newcomer", xp=5000)
        self.assertNotIn("newcomer", self.names(self.page(self.players[0])))     # cached
        cache.clear()
        self.assertEqual(self.names(self.page(self.players[0]))[0], "newcomer")


class PrivacyTests(BoardTestCase):
    def test_only_public_fields_reach_the_page(self):
        users = [player("alpha", xp=30), player("bravo", xp=20), player("charlie", xp=10), player("delta", xp=5)]
        res = self.page(users[0])
        html = res.content.decode()
        for user in users:
            self.assertIn(user.username, html)
            self.assertNotIn(user.email, html)
            self.assertNotIn(user.full_name, html)
        for row in res.context["podium"] + res.context["rows"]:
            self.assertEqual(set(row), {"id", "rank", "username", "initial", "avatar_url", "courses", "xp", "is_me"})

    def test_usernames_are_escaped(self):
        player("x", xp=5)
        User.objects.filter(username="x").update(username="<b>bold</b>")
        res = self.page(User.objects.get(username="<b>bold</b>"))
        self.assertNotContains(res, "<b>bold</b>")
        self.assertContains(res, "&lt;b&gt;bold&lt;/b&gt;")

    def test_signed_out_visitors_are_sent_to_sign_in(self):
        self.assertEqual(self.client.get(reverse("leaderboard:list")).status_code, 302)


class DashboardLinkTests(BoardTestCase):
    def test_dashboard_shows_a_link_not_the_board(self):
        me = player("dash", xp=10)
        player("other", xp=50)
        self.client.force_login(me)
        page = self.client.get(reverse("dashboard:home"))
        self.assertContains(page, "View leaderboard")
        self.assertContains(page, reverse("leaderboard:list"))
        self.assertContains(page, "#2")
        self.assertNotContains(page, "other")
