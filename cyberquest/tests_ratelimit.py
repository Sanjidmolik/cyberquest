"""Tests for cyberquest/ratelimit.py — P2-02 race-condition fix."""

from django.core.cache import cache
from django.test import TestCase, RequestFactory, override_settings

from cyberquest.ratelimit import is_rate_limited, rate_limit


class IsRateLimitedTests(TestCase):
    def setUp(self):
        cache.clear()
        self.key = "test_rl_key"

    def _limited(self, n=1):
        for _ in range(n):
            result = is_rate_limited(self.key, limit=3, window_seconds=60)
        return result

    def test_first_request_not_limited(self):
        self.assertFalse(is_rate_limited(self.key, limit=3, window_seconds=60))

    def test_requests_within_limit_not_blocked(self):
        for _ in range(3):
            self.assertFalse(is_rate_limited(self.key, limit=3, window_seconds=60))

    def test_request_over_limit_is_blocked(self):
        for _ in range(3):
            is_rate_limited(self.key, limit=3, window_seconds=60)
        self.assertTrue(is_rate_limited(self.key, limit=3, window_seconds=60))

    def test_counter_increments_monotonically(self):
        """Atomic add+incr means sequential calls always see increasing counts."""
        for i in range(1, 6):
            is_rate_limited(self.key, limit=10, window_seconds=60)
            self.assertEqual(int(cache.get(self.key)), i)
