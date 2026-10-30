"""One-to-one messaging: access, requests, settings, blocking, rate limits, encryption at rest,
escaping, polling, account deletion, the key check, privacy export, and the WebSocket."""

import json
import re
import tempfile
from io import BytesIO, StringIO
from pathlib import Path

from asgiref.sync import sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from accounts.public import DEFAULT_AVATAR_SVG
from messaging import checks, services
from messaging.models import Block, Conversation, Message, MessagingPreference
from messaging.policy import Denied
from messaging.routing import websocket_urlpatterns

User = get_user_model()


def member(name, **extra):
    return User.objects.create_user(email=f"{name}@example.com", password="testpass123", username=name, **extra)


class MessagingTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.ana, self.bo, self.cy = member("ana"), member("bo"), member("cy")

    def api(self, name, public_id, body=None, user=None, **params):
        if user:
            self.client.force_login(user)
        url = reverse(f"messaging:{name}", args=[public_id])
        if body is None:
            return self.client.get(url, params)
        return self.client.post(url, json.dumps(body), content_type="application/json")

    def talk(self, sender, recipient, text="hello", accept=True):
        conversation, message = services.start(sender, recipient.username, text)
        if accept and conversation.state == Conversation.PENDING:
            services.accept(recipient, conversation)
            conversation.refresh_from_db()
        return conversation, message


class AccessTests(MessagingTestCase):
    def test_non_participants_get_404_everywhere(self):
        conversation, _ = self.talk(self.ana, self.bo)
        pid = conversation.public_id
        self.client.force_login(self.cy)
        for name in ("conversation",):
            self.assertEqual(self.client.get(reverse(f"messaging:{name}", args=[pid])).status_code, 404)
        self.assertEqual(self.api("api_poll", pid).status_code, 404)
        self.assertEqual(self.api("api_send", pid, {"text": "sneaky"}).status_code, 404)
        self.assertEqual(self.api("api_read", pid, {"upto": 999}).status_code, 404)
        for name in ("accept", "decline"):
            self.assertEqual(self.client.post(reverse(f"messaging:{name}", args=[pid])).status_code, 404)
        self.assertEqual(Message.objects.count(), 1)

    def test_signed_out_visitors_are_sent_to_sign_in(self):
        conversation, _ = self.talk(self.ana, self.bo)
        for url in (reverse("messaging:inbox"), reverse("messaging:new"), reverse("messaging:settings"),
                    reverse("messaging:api_inbox"), reverse("messaging:api_poll", args=[conversation.public_id])):
            self.assertEqual(self.client.get(url).status_code, 302, url)

    def test_participants_can_read_their_conversation(self):
        conversation, _ = self.talk(self.ana, self.bo)
        for user in (self.ana, self.bo):
            res = self.api("api_poll", conversation.public_id, user=user)
            self.assertEqual(res.json()["messages"][0]["text"], "hello")

    def test_posts_need_csrf(self):
        from django.test import Client
        conversation, _ = self.talk(self.ana, self.bo)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.ana)
        res = client.post(reverse("messaging:api_send", args=[conversation.public_id]),
                          json.dumps({"text": "x"}), content_type="application/json")
        self.assertEqual(res.status_code, 403)


class RequestTests(MessagingTestCase):
    def test_first_message_from_someone_new_is_a_request_until_accepted(self):
        conversation, _ = services.start(self.ana, "bo", "Hi Bo")
        self.assertEqual((conversation.state, conversation.initiator), (Conversation.PENDING, self.ana))
        self.assertEqual([r["username"] for r in services.inbox(self.bo, "requests")], ["ana"])
        self.assertEqual(services.inbox(self.bo, "inbox"), [])
        self.assertTrue(services.inbox(self.ana, "inbox")[0]["waiting"])
        with self.assertRaises(Denied):
            services.send(self.bo, conversation, "reply before accepting")
        services.send(self.ana, conversation, "one more")                       # the sender may add more
        services.accept(self.bo, conversation)
        conversation.refresh_from_db()
        self.assertEqual(conversation.state, Conversation.ACCEPTED)
        services.send(self.bo, conversation, "hi!")
        self.assertEqual([r["username"] for r in services.inbox(self.bo, "inbox")], ["ana"])

    def test_request_page_offers_accept_and_hides_the_reply_box(self):
        conversation, _ = services.start(self.ana, "bo", "Hi")
        self.client.force_login(self.bo)
        page = self.client.get(reverse("messaging:conversation", args=[conversation.public_id]))
        self.assertContains(page, 'id="msg-compose" hidden')
        self.assertContains(page, "Accept this request to reply.")
        self.assertContains(page, reverse("messaging:accept", args=[conversation.public_id]))
        self.client.post(reverse("messaging:accept", args=[conversation.public_id]))
        page = self.client.get(reverse("messaging:conversation", args=[conversation.public_id]))
        self.assertNotContains(page, 'id="msg-compose" hidden')

    def test_only_the_recipient_accepts_or_declines(self):
        conversation, _ = services.start(self.ana, "bo", "Hi")
        with self.assertRaises(Denied):
            services.accept(self.ana, conversation)
        services.decline(self.bo, conversation)
        conversation.refresh_from_db()
        self.assertEqual(conversation.state, Conversation.DECLINED)
        with self.assertRaises(Denied):
            services.start(self.ana, "bo", "please?")
        self.assertEqual(services.inbox(self.bo, "requests"), [])
        # Bo can still start writing later, which accepts the conversation.
        services.start(self.bo, "ana", "Changed my mind")
        conversation.refresh_from_db()
        self.assertEqual(conversation.state, Conversation.ACCEPTED)

    def test_nobody_setting_stops_new_requests_but_not_accepted_conversations(self):
        friends, _ = self.talk(self.ana, self.bo)
        services.set_preference(self.bo, MessagingPreference.NOBODY)
        with self.assertRaises(Denied):
            services.start(self.cy, "bo", "hi")
        services.send(self.ana, friends, "still fine")
        self.client.force_login(self.bo)
        page = self.client.post(reverse("messaging:settings"), {"who_can_message": "everyone"})
        self.assertEqual(page.status_code, 302)
        self.assertEqual(services.preference(self.bo), "everyone")

    def test_one_conversation_per_pair_and_no_self_messages(self):
        first, _ = self.talk(self.ana, self.bo)
        again, _ = services.start(self.bo, "ana", "same thread")
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(Conversation.objects.count(), 1)
        with self.assertRaises(Denied):
            services.start(self.ana, "ana", "me")
        with self.assertRaises(Denied):
            services.start(self.ana, "nobody-here", "hi")

    def test_text_only_up_to_2000_characters(self):
        conversation, _ = self.talk(self.ana, self.bo)
        ok = self.api("api_send", conversation.public_id, {"text": "x" * 2000}, user=self.ana)
        self.assertEqual(ok.status_code, 201)
        for text in ("x" * 2001, "   ", None):
            self.assertEqual(self.api("api_send", conversation.public_id, {"text": text}).status_code, 400)


class BlockTests(MessagingTestCase):
    def test_blocked_users_cannot_message_either_way_or_find_you(self):
        conversation, _ = self.talk(self.ana, self.bo)
        services.block(self.bo, self.ana)
        for sender in (self.ana, self.bo):
            with self.assertRaises(Denied):
                services.send(sender, conversation, "hi")
        with self.assertRaises(Denied):
            services.start(self.ana, "bo", "new")
        self.assertEqual([p["username"] for p in services.search_people(self.ana, "bo")], [])
        self.assertEqual([p["username"] for p in services.search_people(self.cy, "bo")], ["bo"])
        services.unblock(self.bo, self.ana)
        services.send(self.ana, conversation, "back again")

    def test_card_and_photo_of_someone_who_blocked_you_are_hidden(self):
        from accounts.public import public_card
        conversation, _ = self.talk(self.ana, self.bo)
        self.assertIsNotNone(public_card(self.bo, self.ana))
        services.block(self.bo, self.ana)
        self.assertIsNone(public_card(self.bo, self.ana))
        self.assertIsNotNone(public_card(self.ana, self.bo))       # only the blocker is hidden
        self.client.force_login(self.ana)
        page = self.client.get(reverse("messaging:conversation", args=[conversation.public_id]))
        self.assertIsNone(page.context["card"])
        self.assertNotContains(page, "msg-card-meta")              # no card stats
        self.assertNotContains(page, reverse("accounts:avatar", args=[self.bo.avatar_token]))

    def test_block_and_unblock_through_the_pages(self):
        self.client.force_login(self.ana)
        self.client.post(reverse("messaging:block"), {"username": "bo"})
        self.assertTrue(Block.objects.filter(blocker=self.ana, blocked=self.bo).exists())
        self.assertContains(self.client.get(reverse("messaging:settings")), "bo")
        self.client.post(reverse("messaging:unblock"), {"username": "bo", "next": "https://evil.example/"})
        self.assertFalse(Block.objects.exists())


@override_settings(MESSAGING_MESSAGES_PER_MINUTE=3, MESSAGING_NEW_CONVERSATIONS_PER_DAY=2)
class RateLimitTests(MessagingTestCase):
    def test_messages_per_minute(self):
        conversation, _ = self.talk(self.ana, self.bo)      # message 1
        for _ in range(2):
            self.assertEqual(self.api("api_send", conversation.public_id, {"text": "x"}, user=self.ana).status_code, 201)
        res = self.api("api_send", conversation.public_id, {"text": "too many"})
        self.assertEqual(res.status_code, 429)
        self.assertIn("too quickly", res.json()["error"])
        # Limits are per user.
        self.assertEqual(self.api("api_send", conversation.public_id, {"text": "mine"}, user=self.bo).status_code, 201)

    def test_new_conversations_per_day(self):
        dee = member("dee")
        services.start(self.ana, "bo", "1")
        services.start(self.ana, "cy", "2")
        with self.assertRaises(Denied) as caught:
            services.start(self.ana, "dee", "3")
        self.assertIn("new conversations", str(caught.exception))
        services.start(dee, "ana", "others can still write to ana")


class EncryptionTests(MessagingTestCase):
    def test_text_is_encrypted_in_the_database_and_decrypts(self):
        _, message = self.talk(self.ana, self.bo, "my secret plan")
        with connection.cursor() as cursor:
            cursor.execute("SELECT body FROM messaging_message WHERE id = %s", [message.pk])
            stored = cursor.fetchone()[0]
        self.assertNotIn("secret", stored)
        self.assertTrue(stored.startswith("gAAAA"))                  # a Fernet token
        self.assertEqual(Message.objects.get(pk=message.pk).text, "my secret plan")
        _, again = services.start(self.ana, "bo", "my secret plan")
        self.assertNotEqual(Message.objects.get(pk=again.pk).body, stored)    # random IV each time

    def test_rotation_reencrypts_with_the_newest_key(self):
        _, message = self.talk(self.ana, self.bo, "rotate me")
        old_keys = list(settings.MESSAGE_ENCRYPTION_KEYS)
        new_key = Fernet.generate_key().decode()
        with override_settings(MESSAGE_ENCRYPTION_KEYS=[new_key] + old_keys):
            out = StringIO()
            call_command("rotate_message_keys", stdout=out)
            self.assertIn("Re-encrypted", out.getvalue())
        body = Message.objects.get(pk=message.pk).body
        self.assertEqual(Fernet(new_key.encode()).decrypt(body.encode()).decode(), "rotate me")
        with override_settings(MESSAGE_ENCRYPTION_KEYS=[new_key]):     # old key removed: still readable
            self.assertEqual(Message.objects.get(pk=message.pk).text, "rotate me")

    def test_system_check_errors_without_a_valid_key(self):
        with override_settings(MESSAGE_ENCRYPTION_KEYS=[]):
            self.assertEqual([e.id for e in checks.message_key_configured(None)], ["messaging.E001"])
        with override_settings(MESSAGE_ENCRYPTION_KEYS=["not-a-key"]):
            self.assertEqual([e.id for e in checks.message_key_configured(None)], ["messaging.E002"])
        self.assertEqual(checks.message_key_configured(None), [])


class EscapingTests(MessagingTestCase):
    PAYLOAD = '<script>alert("x")</script><img src=x onerror=alert(1)>'

    def test_message_text_is_never_rendered_as_html(self):
        conversation, _ = self.talk(self.ana, self.bo, self.PAYLOAD)
        self.client.force_login(self.bo)
        for url in (reverse("messaging:inbox"), reverse("messaging:conversation", args=[conversation.public_id])):
            html = self.client.get(url).content.decode()
            self.assertNotIn("<script>alert", html)
            self.assertNotIn("<img src=x", html)
        page = self.client.get(reverse("messaging:inbox")).content.decode()
        self.assertIn("&lt;script&gt;", page)                        # inbox preview, autoescaped
        res = self.api("api_poll", conversation.public_id)
        self.assertEqual(res["Content-Type"], "application/json")
        self.assertEqual(res.json()["messages"][0]["text"], self.PAYLOAD)   # data, shown via textContent

    def test_script_and_templates_never_inject_html(self):
        base = Path(settings.BASE_DIR) / "messaging"
        script = (base / "static/messaging/js/messaging.js").read_text(encoding="utf-8")
        for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(unsafe, script)
        for template in (base / "templates/messaging").glob("*.html"):
            text = template.read_text(encoding="utf-8")
            self.assertNotIn("|safe", text, template.name)
            self.assertNotIn("autoescape off", text, template.name)


class PollingTests(MessagingTestCase):
    def test_poll_returns_only_newer_messages_and_unread_counts_follow_reads(self):
        conversation, first = self.talk(self.ana, self.bo, "one")
        second = services.send(self.ana, conversation, "two")
        third = services.send(self.ana, conversation, "three")
        res = self.api("api_poll", conversation.public_id, user=self.bo, after=first.pk).json()
        self.assertEqual([m["text"] for m in res["messages"]], ["two", "three"])
        self.assertTrue(res["status"]["can_send"])
        older = self.api("api_poll", conversation.public_id, before=third.pk).json()
        self.assertEqual([m["text"] for m in older["messages"]], ["one", "two"])
        self.assertEqual(self.client.get(reverse("messaging:api_inbox")).json()["rows"][0]["unread"], 3)
        self.api("api_read", conversation.public_id, {"upto": second.pk})
        self.assertEqual(self.client.get(reverse("messaging:api_inbox")).json()["rows"][0]["unread"], 1)
        self.api("api_read", conversation.public_id, {"upto": 10 ** 12})             # capped at the newest
        conversation.refresh_from_db()
        self.assertEqual(conversation.read_upto(self.bo), third.pk)
        self.assertEqual(self.client.get(reverse("messaging:api_inbox")).json()["rows"][0]["unread"], 0)
        # The sender's own messages are never unread for them.
        self.client.force_login(self.ana)
        self.assertEqual(self.client.get(reverse("messaging:api_inbox")).json()["rows"][0]["unread"], 0)

    def test_inbox_search_is_by_username(self):
        self.talk(self.ana, self.bo)
        self.talk(self.ana, self.cy)
        self.client.force_login(self.ana)
        rows = self.client.get(reverse("messaging:api_inbox"), {"q": "cy"}).json()["rows"]
        self.assertEqual([r["username"] for r in rows], ["cy"])

    def test_the_script_backs_off_and_pauses(self):
        script = (Path(settings.BASE_DIR) / "messaging/static/messaging/js/messaging.js").read_text(encoding="utf-8")
        for needle in ("FAST = 4000", "SLOW = 15000", "IDLE_AFTER = 120000", "document.hidden", "?after="):
            self.assertIn(needle, script)


class DeletedAccountTests(MessagingTestCase):
    def test_deleted_users_messages_show_as_deleted_with_text_removed(self):
        conversation, message = self.talk(self.ana, self.bo, "remember me")
        services.send(self.bo, conversation, "bo stays")
        self.ana.delete()
        stored = Message.objects.get(pk=message.pk)
        self.assertEqual((stored.sender, stored.body, stored.removed, stored.text), (None, "", True, ""))
        res = self.api("api_poll", conversation.public_id, user=self.bo).json()
        self.assertEqual([(m["sender"], m["text"], m["removed"]) for m in res["messages"]],
                         [(None, "", True), ("bo", "bo stays", False)])
        self.assertFalse(res["status"]["can_send"])
        row = services.inbox(self.bo)[0]
        self.assertIsNone(row["username"])
        self.assertContains(self.client.get(reverse("messaging:inbox")), "Deleted user")


class PrivacyExportTests(MessagingTestCase):
    def test_export_includes_messages_settings_and_blocks(self):
        from accounts.privacy import build_export, export_zip_bytes
        self.talk(self.ana, self.bo, "for the export")
        services.block(self.ana, self.cy)
        services.set_preference(self.ana, "nobody")
        data = build_export(self.ana)
        self.assertEqual([(m["with"], m["from"], m["text"]) for m in data["messages"]], [("bo", "you", "for the export")])
        self.assertEqual(data["message_settings"], {"who_can_message": "nobody", "read_receipts": True,
                                                    "show_online": True, "default_timer": "off",
                                                    "last_active_in_messages": None})
        self.assertEqual([b["username"] for b in data["blocked_members"]], ["cy"])
        import zipfile
        names = zipfile.ZipFile(BytesIO(export_zip_bytes(self.ana))).namelist()
        self.assertTrue({"messages.csv", "blocked_members.csv", "message_settings.csv"} <= set(names))

    def test_retention_lists_messages_and_blocks(self):
        from accounts.retention import RETENTION
        records = " ".join(row[0] for row in RETENTION)
        self.assertIn("Messages you send and receive", records)
        self.assertIn("members you blocked", records)
        self.client.force_login(self.ana)
        self.assertContains(self.client.get(reverse("pages:privacy")), "not end-to-end")


class ProtectionNoteTests(MessagingTestCase):
    def test_inbox_explains_protection_honestly(self):
        self.client.force_login(self.ana)
        page = self.client.get(reverse("messaging:inbox")).content.decode()
        self.assertIn("How your messages are protected", page)
        # v2 wording (D5): the app states what is true; the "not end-to-end" sentence is in the Privacy Policy.
        self.assertIn("Encrypted in transit and at rest. Moderators can review messages only if they’re reported.", page)
        self.assertNotRegex(page, re.compile("end-to-end", re.I))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AvatarTests(MessagingTestCase):
    def _photo(self, user):
        from PIL import Image
        buffer = BytesIO()
        Image.new("RGB", (8, 8), (1, 2, 3)).save(buffer, format="PNG")
        user.profile_picture.save("face.png", ContentFile(buffer.getvalue()), save=True)

    def _get(self, token):
        res = self.client.get(f"/accounts/avatar/{token}/")
        body = b"".join(res.streaming_content) if res.streaming else res.content
        return res.status_code, res["Content-Type"], body

    def test_tokens_serve_the_photo_or_the_same_default(self):
        self._photo(self.bo)
        self.client.force_login(self.ana)
        status, kind, body = self._get(self.bo.avatar_token)
        self.assertEqual((status, kind), (200, "image/png"))
        default = self._get(self.cy.avatar_token)                         # no photo
        self.assertEqual(default, (200, "image/svg+xml", DEFAULT_AVATAR_SVG))
        for guess in ("x" * 24, "..", "%2e%2e", "1", str(self.bo.pk), "profile_pictures", "y" * 40):
            self.assertEqual(self._get(guess), default, guess)               # nothing to learn by guessing
        services.block(self.bo, self.ana)
        self.assertEqual(self._get(self.bo.avatar_token), default)          # blocked: default for ana
        self.client.force_login(self.cy)
        self.assertEqual(self._get(self.bo.avatar_token)[1], "image/png")   # others still see it

    def test_tokens_are_random_and_unique(self):
        tokens = [u.avatar_token for u in (self.ana, self.bo, self.cy)]
        self.assertEqual(len(set(tokens)), 3)
        self.assertTrue(all(len(t) == 24 and not t.isdigit() for t in tokens))

    def test_the_numeric_photo_route_is_gone(self):
        with self.assertRaises(NoReverseMatch):
            reverse("accounts:profile_photo", args=[1])
        self.client.force_login(self.ana)
        self.assertEqual(self.client.get(f"/accounts/photo/{self.bo.pk}/").status_code, 404)

    def test_no_numeric_user_ids_in_leaderboard_inbox_or_cards(self):
        cache.clear()
        # Distinctive ids that can't be confused with ranks, XP, counts or times.
        ids = {name: 987650 + n for n, name in enumerate(("zed", "yan", "id0", "id1"))}
        users = {name: member(name, id=pk) for name, pk in ids.items()}
        User.objects.filter(username__in=["id0", "id1"]).update(xp=500)
        ana, bo = users["zed"], users["yan"]
        self._photo(bo)
        conversation, _ = self.talk(ana, bo, "hello")
        self.client.force_login(ana)
        pages = [
            self.client.get(reverse("leaderboard:list")),
            self.client.get(reverse("messaging:inbox")),
            self.client.get(reverse("messaging:conversation", args=[conversation.public_id])),
            self.client.get(reverse("messaging:new"), {"q": "id"}),
            self.client.get(reverse("dashboard:home")),
        ]
        for page in pages:
            html = page.content.decode()
            self.assertEqual(page.status_code, 200)
            for pk in ids.values():
                self.assertNotIn(str(pk), html, page.wsgi_request.path)
        self.assertIn(reverse("accounts:avatar", args=[bo.avatar_token]), pages[2].content.decode())


class SocketTests(MessagingTestCase):
    """The consumer, with the user put in the scope as AuthMiddleware would."""

    def _app(self, user):
        router = URLRouter(websocket_urlpatterns)

        async def app(scope, receive, send):
            return await router({**scope, "user": user}, receive, send)
        return app

    async def _connect(self, user):
        communicator = WebsocketCommunicator(self._app(user), "/ws/messages/")
        connected, code = await communicator.connect()
        return communicator, connected, code

    async def test_anonymous_and_inactive_sockets_are_refused(self):
        from django.contrib.auth.models import AnonymousUser
        _, connected, code = await self._connect(AnonymousUser())
        self.assertFalse(connected)
        self.assertEqual(code, 4401)
        gone = await sync_to_async(member)("gone", is_active=False)
        _, connected, _ = await self._connect(gone)
        self.assertFalse(connected)

    async def test_participants_get_a_push_others_dont(self):
        conversation, _ = await sync_to_async(self.talk)(self.ana, self.bo)
        ana_socket, ok, _ = await self._connect(self.ana)
        cy_socket, ok2, _ = await self._connect(self.cy)
        self.assertTrue(ok and ok2)
        def send():                       # pushes go out on commit; TestCase never commits
            with self.captureOnCommitCallbacks(execute=True):
                services.send(self.bo, conversation, "ping ana")
        await sync_to_async(send)()
        event = await ana_socket.receive_json_from(timeout=2)
        self.assertEqual((event["type"], event["conversation"]), ("changed", str(conversation.public_id)))
        self.assertNotIn("text", json.dumps(event))                       # never carries message text
        self.assertTrue(await cy_socket.receive_nothing(timeout=0.3))
        await ana_socket.disconnect()
        await cy_socket.disconnect()

    async def test_membership_is_checked_for_every_event_and_frame(self):
        conversation, _ = await sync_to_async(self.talk)(self.ana, self.bo)
        cy_socket, _, _ = await self._connect(self.cy)
        # A forged event for a conversation cy isn't in is dropped.
        from channels.layers import get_channel_layer
        from messaging.events import user_group
        await get_channel_layer().group_send(user_group(self.cy.pk), {
            "type": "conversation.changed", "conversation": str(conversation.public_id), "id": 1})
        self.assertTrue(await cy_socket.receive_nothing(timeout=0.3))
        await cy_socket.send_json_to({"type": "watch", "conversation": str(conversation.public_id)})
        self.assertEqual(await cy_socket.receive_json_from(), {"type": "watch", "ok": False})
        await cy_socket.send_json_to({"type": "watch", "conversation": "not-a-uuid"})
        self.assertEqual(await cy_socket.receive_json_from(), {"type": "watch", "ok": False})
        await cy_socket.send_json_to({"type": "send", "text": "hi"})
        self.assertEqual((await cy_socket.receive_json_from())["type"], "error")
        await cy_socket.disconnect()
        ana_socket, _, _ = await self._connect(self.ana)
        await ana_socket.send_json_to({"type": "watch", "conversation": str(conversation.public_id)})
        self.assertEqual(await ana_socket.receive_json_from(), {"type": "watch", "ok": True})
        await ana_socket.disconnect()

    async def test_full_stack_rejects_foreign_origins_and_needs_a_session(self):
        from cyberquest.asgi import application
        evil = WebsocketCommunicator(application, "/ws/messages/", headers=[(b"origin", b"https://evil.example")])
        connected, _ = await evil.connect()
        self.assertFalse(connected)
        anonymous = WebsocketCommunicator(application, "/ws/messages/", headers=[(b"origin", b"http://testserver")])
        connected, _ = await anonymous.connect()
        self.assertFalse(connected)
        await sync_to_async(self.client.force_login)(self.ana)
        cookie = f"sessionid={self.client.cookies['sessionid'].value}".encode()
        signed_in = WebsocketCommunicator(application, "/ws/messages/",
                                          headers=[(b"origin", b"http://testserver"), (b"cookie", cookie)])
        connected, _ = await signed_in.connect()
        self.assertTrue(connected)
        await signed_in.disconnect()
