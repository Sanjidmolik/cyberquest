"""Messaging v2, step 1: disappearing messages.

Timer changes leave a system notice and apply to later messages only; expired messages are
never returned by any page, API, export or report even before cleanup; the cleanup job and
the in-request sweep delete rows (and photo files) and are idempotent; reports keep content."""

import json
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.privacy import build_export
from accounts.retention import run_all
from messaging import expiry, services
from messaging.models import Conversation, Message, MessagingPreference
from messaging.policy import Denied, RateLimited
from moderation import services as moderation
from moderation.models import Report

User = get_user_model()


def member(name, **extra):
    return User.objects.create_user(email=f"{name}@example.com", password="testpass123", username=name, **extra)


class ExpiryTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.ana, self.bo, self.cy = member("ana"), member("bo"), member("cy")
        self.conversation, _ = services.start(self.ana, "bo", "hello")
        services.accept(self.bo, self.conversation)
        self.conversation.refresh_from_db()

    def timer(self, user, value, conversation=None):
        self.client.force_login(user)
        return self.client.post(reverse("messaging:api_timer", args=[(conversation or self.conversation).public_id]),
                                json.dumps({"timer": value}), content_type="application/json")

    def expire(self, message):
        Message.all_objects.filter(pk=message.pk).update(expires_at=timezone.now() - timedelta(seconds=1))


class TimerTests(ExpiryTestCase):
    def test_either_participant_changes_it_with_a_system_notice(self):
        res = self.timer(self.bo, "24h")
        self.assertEqual(res.status_code, 200)
        notice = Message.objects.get(kind=Message.SYSTEM)
        self.assertEqual(notice.text, "bo set disappearing messages to 24 hours")
        self.assertIsNone(notice.expires_at)                      # notices never disappear
        self.assertEqual(res.json()["message"]["kind"], "system")
        self.assertFalse(res.json()["message"]["can_report"])
        self.assertEqual(Conversation.objects.get(pk=self.conversation.pk).disappear_after, "24h")
        self.assertEqual(self.timer(self.ana, "off").status_code, 200)
        self.assertEqual(Message.objects.filter(kind=Message.SYSTEM).last().text,
                         "ana turned off disappearing messages")
        self.assertIsNone(self.timer(self.ana, "off").json()["message"])   # unchanged: no new notice
        self.assertEqual(Message.objects.filter(kind=Message.SYSTEM).count(), 2)

    def test_applies_only_to_messages_sent_after_the_change(self):
        before = services.send(self.ana, self.conversation, "before")
        self.timer(self.ana, "1h")
        after = services.send(self.ana, self.conversation, "after")
        before.refresh_from_db()
        self.assertIsNone(before.expires_at)
        self.assertEqual(after.timer, "1h")
        self.assertAlmostEqual((after.expires_at - after.created_at).total_seconds(), 3600, delta=1)

    def test_bad_values_outsiders_and_request_recipients_are_refused(self):
        self.assertEqual(self.timer(self.ana, "forever").status_code, 400)
        self.assertEqual(self.timer(self.ana, "").status_code, 400)
        self.assertEqual(self.timer(self.cy, "1h").status_code, 404)
        request, _ = services.start(self.cy, "bo", "hi")
        self.assertEqual(self.timer(self.bo, "1h", request).status_code, 400)       # must accept first
        self.client.force_login(self.ana)
        url = reverse("messaging:api_timer", args=[self.conversation.public_id])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertFalse(Message.objects.filter(kind=Message.SYSTEM).exists())

    def test_timer_changes_are_rate_limited(self):
        with self.settings(MESSAGING_TIMER_CHANGES_PER_HOUR=2):
            services.set_timer(self.ana, self.conversation, "1h")
            services.set_timer(self.ana, self.conversation, "off")
            with self.assertRaises(RateLimited):
                services.set_timer(self.ana, self.conversation, "24h")

    def test_new_chats_take_the_starters_default_timer(self):
        MessagingPreference.objects.create(user=self.cy, default_timer="7d")
        conversation, message = services.start(self.cy, "ana", "hey")
        self.assertEqual(conversation.disappear_after, "7d")
        notice, first = conversation.messages.order_by("pk")
        self.assertEqual((notice.kind, notice.text), (Message.SYSTEM, "cy set disappearing messages to 7 days"))
        self.assertEqual(first.timer, "7d")
        self.assertIsNotNone(first.expires_at)

    def test_after_viewing_starts_30_seconds_after_the_recipient_reads(self):
        services.set_timer(self.ana, self.conversation, "view")
        message = services.send(self.ana, self.conversation, "read me once")
        self.assertIsNone(message.expires_at)
        services.mark_read(self.ana, self.conversation, message.pk)          # the sender reading changes nothing
        message.refresh_from_db()
        self.assertIsNone(message.expires_at)
        services.mark_read(self.bo, self.conversation, message.pk)
        message.refresh_from_db()
        self.assertAlmostEqual((message.expires_at - timezone.now()).total_seconds(), 30, delta=2)


class NeverServedTests(ExpiryTestCase):
    """An expired message is gone from every endpoint before the cleanup job runs."""

    def test_expired_messages_are_hidden_everywhere(self):
        services.set_timer(self.ana, self.conversation, "1h")
        secret = services.send(self.ana, self.conversation, "expired secret text")
        self.expire(secret)
        self.assertTrue(Message.all_objects.filter(pk=secret.pk).exists())    # still in the table
        pid = self.conversation.public_id
        self.client.force_login(self.bo)
        pages = [
            self.client.get(reverse("messaging:api_poll", args=[pid])),
            self.client.get(reverse("messaging:api_poll", args=[pid]), {"after": 0}),
            self.client.get(reverse("messaging:api_poll", args=[pid]), {"before": secret.pk + 10}),
            self.client.get(reverse("messaging:api_inbox")),
            self.client.get(reverse("messaging:conversation", args=[pid])),
            self.client.get(reverse("messaging:inbox")),
        ]
        for page in pages:
            self.assertEqual(page.status_code, 200)
            self.assertNotIn("expired secret text", page.content.decode(), page.wsgi_request.get_full_path())
        rows = services.inbox(self.bo)
        self.assertEqual(rows[0]["unread"], 2)                    # "hello" and the notice, not the expired one
        self.assertNotIn("expired secret text", json.dumps(build_export(self.bo), default=str))
        self.assertNotIn("expired secret text", json.dumps(build_export(self.ana), default=str))
        with self.assertRaises(Denied):
            moderation.report(self.bo, secret.pk, "spam")
        services.mark_read(self.bo, self.conversation, secret.pk)  # read pointer stops at visible messages
        self.assertLess(Conversation.objects.get(pk=self.conversation.pk).b_read_upto, secret.pk)

    def test_report_snapshots_skip_expired_context(self):
        services.set_timer(self.ana, self.conversation, "1h")
        gone = services.send(self.ana, self.conversation, "expired context")
        services.set_timer(self.ana, self.conversation, "off")
        reported = services.send(self.ana, self.conversation, "reported text")
        self.expire(gone)
        report, _ = moderation.report(self.bo, reported.pk, "spam")
        mod = member("mod", is_staff=True)
        rows, _ = moderation.reveal(mod, report)
        texts = [row["text"] for row in rows]
        self.assertIn("reported text", texts)
        self.assertNotIn("expired context", texts)


class CleanupTests(ExpiryTestCase):
    def test_command_deletes_rows_and_files_and_is_idempotent(self):
        services.set_timer(self.ana, self.conversation, "1h")
        texts = [services.send(self.ana, self.conversation, f"m{n}") for n in range(3)]
        keep = services.send(self.ana, self.conversation, "still live")
        photo = Message.all_objects.create(conversation=self.conversation, sender=self.ana, kind=Message.PHOTO,
                                           body="", timer="1h", expires_at=timezone.now())
        photo.photo.save("x.bin", ContentFile(b"ciphertext"), save=True)
        storage = Message._meta.get_field("photo").storage
        name = photo.photo.name
        self.assertTrue(storage.exists(name))
        for message in texts + [photo]:
            self.expire(message)
        dry = StringIO()
        call_command("purge_expired_messages", "--dry-run", stdout=dry)
        self.assertIn("Would delete 4 expired messages and 1 photo files", dry.getvalue())
        self.assertEqual(Message.all_objects.filter(pk__in=[m.pk for m in texts]).count(), 3)
        out = StringIO()
        with self.assertLogs("messaging.expiry", "INFO") as logs:
            call_command("purge_expired_messages", stdout=out)
        self.assertIn("Deleted 4 expired messages and 1 photo files", out.getvalue())
        self.assertFalse(Message.all_objects.filter(pk__in=[m.pk for m in texts + [photo]]).exists())
        self.assertFalse(storage.exists(name))
        self.assertTrue(Message.objects.filter(pk=keep.pk).exists())
        for line in logs.output:                                   # counts only
            self.assertNotIn("m0", line)
            self.assertNotIn("ana", line)
        again = StringIO()
        call_command("purge_expired_messages", stdout=again)
        self.assertIn("Deleted 0 expired messages", again.getvalue())

    def test_reports_keep_the_content_after_the_message_is_deleted(self):
        services.set_timer(self.ana, self.conversation, "24h")
        message = services.send(self.ana, self.conversation, "nasty words")
        report, _ = moderation.report(self.bo, message.pk, "harassment")
        self.expire(message)
        expiry.purge()
        report.refresh_from_db()
        self.assertIsNone(report.message_id)
        rows, _ = moderation.reveal(member("mod", is_staff=True), report)
        self.assertIn("nasty words", [row["text"] for row in rows])

    def test_sweep_runs_at_most_once_a_minute_one_request_at_a_time_in_small_batches(self):
        services.set_timer(self.ana, self.conversation, "1h")
        Message.all_objects.bulk_create([
            Message(conversation=self.conversation, sender=self.ana, body="", timer="1h",
                    expires_at=timezone.now() - timedelta(minutes=1)) for _ in range(expiry.SWEEP_BATCH + 5)])
        cache.add(expiry.SWEEP_LOCK_KEY, 1, 60)                   # another request is sweeping
        self.assertIsNone(expiry.maybe_sweep())
        cache.clear()
        self.assertEqual(expiry.maybe_sweep()["messages"], expiry.SWEEP_BATCH)
        self.assertIsNone(expiry.maybe_sweep())                   # within the minute: nothing
        self.assertEqual(Message.all_objects.filter(expires_at__lte=timezone.now()).count(), 5)
        self.assertFalse(cache.get(expiry.SWEEP_LOCK_KEY))         # the lock is released

    def test_sweep_runs_from_messaging_endpoints_and_never_breaks_them(self):
        services.set_timer(self.ana, self.conversation, "1h")
        self.expire(services.send(self.ana, self.conversation, "old"))
        self.client.force_login(self.bo)
        self.assertEqual(self.client.get(reverse("messaging:api_inbox")).status_code, 200)
        self.assertFalse(Message.all_objects.filter(expires_at__lte=timezone.now()).exists())
        cache.clear()
        from unittest import mock
        with mock.patch("messaging.expiry.purge_batch", side_effect=RuntimeError("db down")):
            self.assertEqual(self.client.get(reverse("messaging:api_inbox")).status_code, 200)

    def test_the_daily_job_is_a_backstop(self):
        services.set_timer(self.ana, self.conversation, "1h")
        self.expire(services.send(self.ana, self.conversation, "old"))
        self.assertEqual(run_all()["expired_disappearing_messages"], 1)
        self.assertEqual(run_all()["expired_disappearing_messages"], 0)

    def test_deleting_an_account_clears_text_of_expired_rows_too(self):
        services.set_timer(self.ana, self.conversation, "1h")
        message = services.send(self.ana, self.conversation, "bye")
        self.expire(message)
        self.ana.delete()
        row = Message.all_objects.get(pk=message.pk)
        self.assertEqual((row.body, row.removed), ("", True))
