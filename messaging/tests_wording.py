"""Messaging v2, step 4: honest wording, copy deterrents, the Privacy Policy, retention and export.

No "end-to-end" or "only you can see" anywhere in the messaging and moderation UI; the exact
"not end-to-end" sentence lives in the Privacy Policy only; timed chats turn off text selection
(a deterrent, stated as one); exports list settings and photo metadata, never photo content;
user text is escaped everywhere it's shown."""

import json
import re
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from accounts.privacy import build_export
from accounts.retention import RETENTION
from messaging import photos, services

User = get_user_model()
APP_PROMISE = "Encrypted in transit and at rest. Moderators can review messages only if they’re reported."


def member(name, **extra):
    return User.objects.create_user(email=f"{name}@example.com", password="testpass123", username=name, **extra)


class WordingTests(TestCase):
    def test_no_end_to_end_or_only_you_can_see_in_messaging_or_moderation_ui(self):
        roots = [Path(settings.BASE_DIR, app, sub) for app in ("messaging", "moderation") for sub in ("templates", "static")]
        files = [p for root in roots if root.exists() for p in root.rglob("*") if p.suffix in (".html", ".js", ".css")]
        self.assertTrue(files)
        for path in files:
            text = path.read_text(encoding="utf-8").lower()
            for phrase in ("end-to-end", "end to end", "only you can see"):
                self.assertNotIn(phrase, text, path)

    def test_the_app_promise_and_the_policy_sentence(self):
        user = member("ana")
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse("messaging:inbox")), APP_PROMISE)
        self.assertContains(self.client.get(reverse("messaging:settings")), APP_PROMISE)
        policy = self.client.get(reverse("pages:privacy"))
        self.assertContains(policy, "This is not end-to-end encryption")
        for phrase in ("Disappearing messages and view-once photos", "can’t block or detect screenshots",
                       "remain in our hosting backups", "until 180 days after the report is resolved"):
            self.assertContains(policy, phrase)

    def test_privacy_panel_says_screenshots_cant_be_blocked(self):
        self.client.force_login(member("ana"))
        page = self.client.get(reverse("messaging:settings"))
        self.assertContains(page, "can’t block or detect screenshots or screen recording")
        self.assertContains(page, "These only discourage copying")

    def test_retention_table_covers_the_new_data(self):
        records = " ".join(row[0] for row in RETENTION)
        for phrase in ("Disappearing messages", "View-once photos", "last active in Messages", "reported view-once photo"):
            self.assertIn(phrase, records)
        self.assertTrue(any("remain in a backup" in row[2] for row in RETENTION))

    def test_user_search_and_list_search_placeholders(self):
        self.client.force_login(member("ana"))
        page = self.client.get(reverse("messaging:inbox"))
        self.assertContains(page, 'placeholder="Search users…"')
        self.assertContains(page, 'placeholder="Search by username…"')


class DeterrentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ana, self.bo = member("ana"), member("bo")
        self.conversation, _ = services.start(self.ana, "bo", "hi")
        services.accept(self.bo, self.conversation)

    def page(self):
        self.client.force_login(self.bo)
        return self.client.get(reverse("messaging:conversation", args=[self.conversation.public_id]))

    def test_copying_is_off_only_while_a_timer_is_on(self):
        page = self.page()
        self.assertNotContains(page, "mx-thread is-nocopy")
        self.assertContains(page, 'id="msg-nocopy" hidden')
        services.set_timer(self.ana, self.conversation, "24h")
        page = self.page()
        self.assertContains(page, "mx-thread is-nocopy")
        self.assertContains(page, "Copying is turned off in this chat")
        self.assertContains(page, 'aria-describedby="msg-nocopy msg-counter"')         # announced to screen readers
        css = Path(settings.BASE_DIR, "messaging/static/messaging/css/messaging.css").read_text(encoding="utf-8")
        rule = re.search(r"\.mx-thread\.is-nocopy[^{]*\{([^}]*)\}", css).group(1)
        self.assertIn("user-select: none", rule)
        self.assertNotIn("display: none", rule)
        thread_tag = page.content.decode().split('id="msg-thread"')[1].split(">")[0]
        self.assertNotIn("aria-hidden", thread_tag)                         # the messages stay readable

    def test_report_dialog_says_the_copy_outlives_the_message(self):
        self.assertContains(self.page(), "A copy is kept for the moderators even if the message disappears")


class ExportAndEscapingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ana, self.bo = member("ana"), member("bo")
        self.conversation, _ = services.start(self.ana, "bo", "hi")
        services.accept(self.bo, self.conversation)

    def test_export_has_settings_timers_and_photo_metadata_only(self):
        services.set_privacy(self.ana, read_receipts=False, show_online=True, default_timer="7d")
        services.set_timer(self.ana, self.conversation, "24h")
        services.send(self.ana, self.conversation, "timed")
        buffer = BytesIO()
        Image.new("RGB", (20, 20), (1, 2, 3)).save(buffer, "PNG")
        photos.send_photo(self.ana, self.conversation, SimpleUploadedFile("p.png", buffer.getvalue(), "image/png"))
        data = build_export(self.ana)
        settings_row = data["message_settings"]
        self.assertEqual((settings_row["read_receipts"], settings_row["show_online"], settings_row["default_timer"]),
                         (False, True, "7d"))
        timed = next(m for m in data["messages"] if m["text"] == "timed")
        self.assertEqual(timed["disappearing"], "24 hours")
        self.assertIsNotNone(timed["expires_at"])
        photo = next(m for m in data["messages"] if m["kind"] == "photo")
        self.assertEqual(photo["text"], "[view-once photo, not opened]")
        dumped = json.dumps(data, default=str)
        self.assertNotIn("msg-photos/", dumped)                                  # no file names, no bytes

    def test_user_text_is_escaped_everywhere(self):
        evil = '<img src=x onerror="alert(1)"></script><script>alert(2)</script>'
        services.send(self.ana, self.conversation, evil)
        self.client.force_login(self.bo)
        for url in (reverse("messaging:inbox"), reverse("messaging:conversation", args=[self.conversation.public_id])):
            html = self.client.get(url).content.decode()
            self.assertNotIn("<script>alert(2)", html)
            self.assertNotIn('<img src=x onerror="alert(1)">', html)
        poll = self.client.get(reverse("messaging:api_poll", args=[self.conversation.public_id]))
        self.assertEqual(poll["Content-Type"], "application/json")
        self.assertIn(evil, [m["text"] for m in poll.json()["messages"]])        # data, not markup
        script = Path(settings.BASE_DIR, "messaging/static/messaging/js/messaging.js").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("insertAdjacentHTML", script)
