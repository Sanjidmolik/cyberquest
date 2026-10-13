"""P2-04: leaderboard rank uses a count query, not a full-table load."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

UserModel = get_user_model()


def _user(email, xp=0, username=None):
    u = UserModel.objects.create_user(
        email=email,
        password="testpass1!",
        username=username or email.split("@")[0],
        ethical_agreement=True,
    )
    u.xp = xp
    u.save(update_fields=["xp"])
    return u


class LeaderboardRankTests(TestCase):
    def setUp(self):
        self.user1 = _user("first@example.com", xp=300, username="first")
        self.user2 = _user("second@example.com", xp=200, username="second")
        self.user3 = _user("third@example.com", xp=100, username="third")

    def test_rank_1_for_top_user(self):
        self.client.force_login(self.user1)
        response = self.client.get(reverse("leaderboard:list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["my_rank"], 1)

    def test_rank_2_for_second_user(self):
        self.client.force_login(self.user2)
        response = self.client.get(reverse("leaderboard:list"))
        self.assertEqual(response.context["my_rank"], 2)

    def test_tied_users_share_rank(self):
        # Create a user with same XP as user2; both should be rank 2.
        tied = _user("tied@example.com", xp=200, username="tied")
        self.client.force_login(tied)
        response = self.client.get(reverse("leaderboard:list"))
        self.assertEqual(response.context["my_rank"], 2)
