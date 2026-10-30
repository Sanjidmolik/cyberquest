"""Messaging v2, step 2: delivery and read receipts, presence, typing, the Privacy panel.

Sent -> delivered (the recipient's client fetched it) -> read (the recipient read it); read
receipts and "online" are reciprocal; a block hides receipts, presence and typing; typing is
WebSocket-only and goes only to the other person of an accepted conversation."""

import json
from datetime import timedelta
from unittest import mock

from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from messaging import services
from messaging.models import Conversation, MessagingPreference
from messaging.routing import websocket_urlpatterns

User = get_user_model()


def member(name, **extra):
    return User.objects.create_user(email=f"{name}@example.com", password="testpass123", username=name, **extra)


class ReceiptsTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.ana, self.bo, self.cy = member("ana"), member("bo"), member("cy")
        self.conversation, self.first = services.start(self.ana, "bo", "hello")
        services.accept(self.bo, self.conversation)
        self.conversation.refresh_from_db()

    def poll(self, user, after=0):
        self.client.force_login(user)
        res = self.client.get(reverse("messaging:api_poll", args=[self.conversation.public_id]), {"after": after})
        self.assertEqual(res.status_code, 200)
        return res.json()

    def read(self, user, upto):
        self.client.force_login(user)
        return self.client.post(reverse("messaging:api_read", args=[self.conversation.public_id]),
                                json.dumps({"upto": upto}), content_type="application/json")

    def status_of(self, user, message):
        rows = {m["id"]: m for m in self.poll(user)["messages"]}
        return rows[message.pk]["status"]

    def privacy(self, user, **values):
        defaults = {"read_receipts": True, "show_online": True, "default_timer": "off"}
        services.set_privacy(user, **{**defaults, **values})


class DeliveryTests(ReceiptsTestCase):
    def test_sent_then_delivered_then_read(self):
        message = services.send(self.ana, self.conversation, "are you there?")
        self.assertEqual(self.status_of(self.ana, message), "sent")
        self.poll(self.bo)                                           # bo's client fetched it
        self.assertEqual(self.status_of(self.ana, message), "delivered")
        self.read(self.bo, message.pk)
        self.assertEqual(self.status_of(self.ana, message), "read")
        data = self.poll(self.ana)
        self.assertEqual(data["receipts"], {"delivered_upto": message.pk, "read_upto": message.pk})

    def test_opening_the_page_or_the_inbox_list_also_delivers(self):
        message = services.send(self.ana, self.conversation, "one")
        services.inbox(self.bo)
        self.assertEqual(self.status_of(self.ana, message), "delivered")
        second = services.send(self.ana, self.conversation, "two")
        self.client.force_login(self.bo)
        self.client.get(reverse("messaging:conversation", args=[self.conversation.public_id]))
        self.assertEqual(self.status_of(self.ana, second), "delivered")

    def test_only_your_own_messages_carry_ticks(self):
        rows = self.poll(self.bo)["messages"]
        self.assertIsNone(rows[0]["status"])                          # ana's message, seen by bo
        services.set_timer(self.ana, self.conversation, "1h")
        notice = [m for m in self.poll(self.ana)["messages"] if m["kind"] == "system"][0]
        self.assertIsNone(notice["status"])                           # notices have no ticks

    def test_changes_push_a_live_update_to_the_sender(self):
        message = services.send(self.ana, self.conversation, "ping")
        with mock.patch("messaging.events.conversation_changed") as push, self.captureOnCommitCallbacks(execute=True):
            services.mark_delivered(self.bo, self.conversation, message.pk)
            services.mark_read(self.bo, self.conversation, message.pk)
        self.assertEqual(push.call_count, 2)
        with mock.patch("messaging.events.conversation_changed") as push, self.captureOnCommitCallbacks(execute=True):
            services.mark_read(self.bo, self.conversation, message.pk)  # nothing new: no push
        push.assert_not_called()


class ReciprocalTests(ReceiptsTestCase):
    def setUp(self):
        super().setUp()
        self.message = services.send(self.ana, self.conversation, "secret plans")
        self.reply = services.send(self.bo, self.conversation, "ok")
        self.poll(self.bo)
        self.read(self.bo, self.reply.pk)
        self.poll(self.ana)
        self.read(self.ana, self.reply.pk)

    def test_both_on_shows_read(self):
        self.assertEqual(self.status_of(self.ana, self.message), "read")
        self.assertEqual(self.status_of(self.bo, self.reply), "read")

    def test_turning_receipts_off_hides_them_both_ways(self):
        self.privacy(self.bo, read_receipts=False)
        self.assertEqual(self.status_of(self.ana, self.message), "delivered")   # bo doesn't send them
        self.assertEqual(self.status_of(self.bo, self.reply), "delivered")      # and stops seeing ana's
        self.assertEqual(self.poll(self.bo)["receipts"]["read_upto"], 0)

    def test_a_block_hides_every_receipt(self):
        services.block(self.bo, self.ana)
        for user, message in ((self.ana, self.message), (self.bo, self.reply)):
            self.assertEqual(self.status_of(user, message), "sent")


class PresenceTests(ReceiptsTestCase):
    def online(self, viewer):
        return self.poll(viewer)["online"]

    def test_accepted_contacts_see_each_other_online(self):
        self.poll(self.bo)                                            # bo's heartbeat
        self.assertTrue(self.online(self.ana))
        rows = services.inbox(self.ana)
        self.assertTrue(rows[0]["online"])

    def test_the_heartbeat_is_throttled_and_goes_stale(self):
        services.touch_presence(self.bo)
        first = MessagingPreference.objects.get(user=self.bo).last_seen_at
        services.touch_presence(self.bo)
        self.assertEqual(MessagingPreference.objects.get(user=self.bo).last_seen_at, first)   # within a minute
        MessagingPreference.objects.filter(user=self.bo).update(last_seen_at=timezone.now() - timedelta(minutes=3))
        self.assertFalse(services.is_online(self.ana, self.conversation))

    def test_show_online_is_reciprocal(self):
        services.touch_presence(self.bo)
        services.touch_presence(self.ana)
        self.privacy(self.ana, show_online=False)
        self.assertFalse(services.is_online(self.bo, self.conversation))   # ana is hidden
        self.assertFalse(services.is_online(self.ana, self.conversation))  # and ana can't see bo

    def test_requests_and_blocks_never_show_presence(self):
        request, _ = services.start(self.cy, "ana", "hi")
        services.touch_presence(self.cy)
        services.touch_presence(self.ana)
        self.assertFalse(services.is_online(self.ana, request))
        self.assertFalse(services.is_online(self.cy, request))
        services.touch_presence(self.bo)
        services.block(self.ana, self.bo)
        self.assertFalse(services.is_online(self.bo, self.conversation))
        self.assertFalse(services.is_online(self.ana, self.conversation))
        self.assertFalse(services.inbox(self.bo)[0]["online"])


class PrivacyPanelTests(ReceiptsTestCase):
    def test_saves_the_privacy_fields(self):
        self.client.force_login(self.ana)
        res = self.client.post(reverse("messaging:settings"), {
            "who_can_message": "everyone", "privacy": "1", "show_online": "on", "default_timer": "24h"})
        self.assertRedirects(res, reverse("messaging:settings"))
        self.assertEqual(services.privacy(self.ana), {"read_receipts": False, "show_online": True, "default_timer": "24h"})
        page = self.client.get(reverse("messaging:settings"))
        self.assertContains(page, "Read receipts")
        self.assertContains(page, '<option value="24h" selected>24 hours</option>', html=True)

    def test_bad_timer_is_refused_and_old_forms_keep_privacy(self):
        self.client.force_login(self.ana)
        self.client.post(reverse("messaging:settings"), {"who_can_message": "everyone", "privacy": "1",
                                                          "default_timer": "forever"})
        self.assertEqual(services.privacy(self.ana)["default_timer"], "off")
        self.privacy(self.ana, read_receipts=False)
        self.client.post(reverse("messaging:settings"), {"who_can_message": "nobody"})
        self.assertFalse(services.privacy(self.ana)["read_receipts"])   # untouched without the panel


class TypingTests(ReceiptsTestCase):
    def _app(self, user):
        router = URLRouter(websocket_urlpatterns)

        async def app(scope, receive, send):
            return await router({**scope, "user": user}, receive, send)
        return app

    async def _connect(self, user):
        communicator = WebsocketCommunicator(self._app(user), "/ws/messages/")
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        return communicator

    async def test_typing_reaches_only_the_other_participant(self):
        ana, bo, cy = await self._connect(self.ana), await self._connect(self.bo), await self._connect(self.cy)
        pid = str(self.conversation.public_id)
        await ana.send_json_to({"type": "typing", "conversation": pid})
        self.assertEqual(await bo.receive_json_from(timeout=2), {"type": "typing", "conversation": pid})
        self.assertTrue(await cy.receive_nothing(timeout=0.3))
        self.assertTrue(await ana.receive_nothing(timeout=0.3))
        await ana.send_json_to({"type": "typing", "conversation": pid})     # throttled: dropped
        self.assertTrue(await bo.receive_nothing(timeout=0.3))
        await cy.send_json_to({"type": "typing", "conversation": pid})      # not a member
        self.assertTrue(await bo.receive_nothing(timeout=0.3))
        for c in (ana, bo, cy):
            await c.disconnect()

    async def test_no_typing_across_a_block_or_in_a_request(self):
        await sync_to_async(services.block)(self.bo, self.ana)
        request, _ = await sync_to_async(services.start)(self.cy, "ana", "hi there")
        ana, bo, cy = await self._connect(self.ana), await self._connect(self.bo), await self._connect(self.cy)
        await ana.send_json_to({"type": "typing", "conversation": str(self.conversation.public_id)})
        self.assertTrue(await bo.receive_nothing(timeout=0.3))
        await cy.send_json_to({"type": "typing", "conversation": str(request.public_id)})
        self.assertTrue(await ana.receive_nothing(timeout=0.3))
        for c in (ana, bo, cy):
            await c.disconnect()

    async def test_bad_frames_are_ignored(self):
        bo = await self._connect(self.bo)
        await bo.send_json_to({"type": "typing", "conversation": "not-a-uuid"})
        self.assertTrue(await bo.receive_nothing(timeout=0.3))
        await bo.disconnect()
