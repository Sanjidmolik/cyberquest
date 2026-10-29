"""Abuse detection, reporting and moderation.

Key promises tested here: detection only warns (no content to moderators, no automatic
punishment); moderators read content only for reported messages and every view is logged;
nobody moderates a report they filed or that is about them; mutes expire; duplicate reports
do nothing; the examples file passes."""

import json
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import URLPattern, reverse
from django.utils import timezone

from messaging import services as msg
from messaging.models import Block, Message
from messaging.policy import Denied
from notifications.models import Notification

from . import detection
from . import services as mod
from .models import AppendOnly, FlagEvent, ModerationLog, Report, Restriction

User = get_user_model()
EXAMPLES = Path(settings.BASE_DIR) / "moderation" / "wordlists" / "examples.txt"


def member(name, **extra):
    return User.objects.create_user(email=f"{name}@example.com", password="testpass123", username=name, **extra)


def moderator(name="mo"):
    user = member(name, is_staff=True)
    user.groups.add(Group.objects.get(name="Moderator"))
    return User.objects.get(pk=user.pk)


class DetectionTests(TestCase):
    def test_every_example_in_the_examples_file(self):
        checked = 0
        for number, line in enumerate(EXAMPLES.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip() or line.startswith("#"):
                continue
            sign, text = line[0], line[2:]
            self.assertIn(sign, "+-", f"line {number}")
            self.assertEqual(detection.may_be_offensive(text), sign == "+", f"line {number}: {text}")
            checked += 1
        self.assertGreaterEqual(checked, 30)

    def test_normalisation_steps(self):
        self.assertEqual(detection.words("id​iot"), ["idiot"])               # zero-width space
        self.assertEqual(detection.words("i­diot"), ["idiot"])               # soft hyphen
        self.assertEqual(detection.words("IDIOOOT"), ["idiot"])                   # case + repeats
        self.assertEqual(detection.words("1d10t!"), ["idiot"])                    # l33t, trailing "!"
        self.assertEqual(detection.words("café"), detection.words("café"))   # NFC
        self.assertEqual(detection.words("হারাম‌জাদা"), detection.words("হারামজাদা"))  # ZWNJ in Bangla
        self.assertTrue(detection.may_be_offensive("তুই হারাম‍জাদা"))

    def test_every_listed_term_matches_itself_and_none_collapses_into_a_common_word(self):
        common = {"as", "pas", "clas", "kil", "lose", "she", "the", "hel", "hi", "you"}
        for phrase in detection.terms():
            self.assertTrue(detection.may_be_offensive(" ".join(phrase)), phrase)
            if len(phrase) == 1:
                self.assertNotIn(phrase[0], common, phrase)


class SendingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ana, self.bo = member("ana"), member("bo")
        self.conversation, _ = msg.start(self.ana, "bo", "hello")
        msg.accept(self.bo, self.conversation)

    def _send(self, text, confirm=False):
        self.client.force_login(self.ana)
        return self.client.post(reverse("messaging:api_send", args=[self.conversation.public_id]),
                                json.dumps({"text": text, "confirm": confirm}), content_type="application/json")

    def test_warning_first_then_send_anyway_records_metadata_only(self):
        res = self._send("you are an idiot")
        self.assertEqual(res.status_code, 409)
        self.assertTrue(res.json()["needs_confirmation"])
        self.assertEqual(Message.objects.count(), 1)                         # nothing sent
        self.assertEqual(list(FlagEvent.objects.values_list("kind", flat=True)), ["warned"])
        self.assertEqual(self._send("you are an idiot", confirm=True).status_code, 201)
        self.assertEqual(sorted(FlagEvent.objects.values_list("kind", flat=True)), ["sent_anyway", "warned"])
        # Metadata only: the model has no field that could hold text or matched words.
        self.assertEqual({f.name for f in FlagEvent._meta.get_fields()}, {"id", "user", "kind", "created_at"})
        self.assertEqual(self._send("thanks for the notes").status_code, 201)
        self.assertEqual(FlagEvent.objects.count(), 2)                        # clean text: nothing recorded

    def test_detection_never_punishes(self):
        for _ in range(5):
            self._send("idiot", confirm=True)
        self.assertFalse(Restriction.objects.exists())
        self.assertFalse(Report.objects.exists())
        self.assertEqual(self._send("still allowed").status_code, 201)

    def test_flag_only_messages_are_never_visible_to_moderators(self):
        self._send("you absolute moron, here is my secret", confirm=True)
        self.client.force_login(moderator())
        html = self.client.get(reverse("moderation:queue")).content.decode()
        self.assertIn("sent 1 flagged message this week", html)
        self.assertNotIn("moron", html)
        self.assertNotIn("secret", html)
        self.assertEqual(mod.flag_counts(), [{"username": "ana", "warned": 0, "sent": 1}])

    def test_new_message_form_shows_the_warning_and_keeps_the_text(self):
        carl = member("carl")
        self.client.force_login(carl)
        page = self.client.post(reverse("messaging:new"), {"username": "bo", "text": "kys"})
        self.assertContains(page, "may be offensive")
        self.assertContains(page, ">kys</textarea>")
        self.assertFalse(Message.objects.filter(sender=carl).exists())
        done = self.client.post(reverse("messaging:new"), {"username": "bo", "text": "kys", "confirm": "1"})
        self.assertEqual(done.status_code, 302)


class ReportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ana, self.bo, self.cy = member("ana"), member("bo"), member("cy")
        self.conversation, _ = msg.start(self.ana, "bo", "first")
        msg.accept(self.bo, self.conversation)
        for n in range(4):
            msg.send(self.ana, self.conversation, f"before {n}")
        self.bad = msg.send(self.ana, self.conversation, "the reported one", confirmed=True)
        for n in range(4):
            msg.send(self.bo, self.conversation, f"after {n}")

    def _report(self, user, message_id, **body):
        self.client.force_login(user)
        payload = {"message": message_id, "reason": "harassment", **body}
        return self.client.post(reverse("moderation_public:report"), json.dumps(payload),
                                content_type="application/json")

    def test_report_keeps_an_encrypted_snapshot_with_three_either_side(self):
        res = self._report(self.bo, self.bad.pk, note="this keeps happening")
        self.assertEqual(res.status_code, 201)
        report = Report.objects.get()
        self.assertEqual((report.reporter, report.reported_user, report.status), (self.bo, self.ana, "open"))
        with connection.cursor() as cursor:
            cursor.execute("SELECT snapshot, note FROM moderation_report")
            snapshot, note = cursor.fetchone()
        self.assertNotIn("reported one", snapshot)
        self.assertNotIn("keeps happening", note)
        rows, note = mod.reveal(moderator(), report)
        self.assertEqual([r["text"] for r in rows],
                         ["before 1", "before 2", "before 3", "the reported one", "after 0", "after 1", "after 2"])
        self.assertEqual([r["reported"] for r in rows].index(True), 3)
        self.assertEqual(note, "this keeps happening")

    def test_reporting_the_same_message_twice_does_nothing(self):
        self.assertEqual(self._report(self.bo, self.bad.pk).status_code, 201)
        again = self._report(self.bo, self.bad.pk, reason="spam")
        self.assertEqual(again.status_code, 200)
        self.assertTrue(again.json()["already_reported"])
        self.assertEqual(Report.objects.count(), 1)
        self.assertEqual(Report.objects.get().reason, "harassment")

    def test_only_received_messages_of_your_own_conversations(self):
        own = Message.objects.filter(sender=self.bo).first()
        self.assertEqual(self._report(self.bo, own.pk).status_code, 400)
        self.assertEqual(self._report(self.cy, self.bad.pk).status_code, 404)        # not a participant
        self.assertEqual(self._report(self.bo, self.bad.pk, reason="nope").status_code, 400)
        self.assertEqual(self._report(self.bo, "1").status_code, 404)
        self.assertFalse(Report.objects.exists())

    def test_also_block_and_rate_limit(self):
        self.assertEqual(self._report(self.bo, self.bad.pk, block=True).status_code, 201)
        self.assertTrue(Block.objects.filter(blocker=self.bo, blocked=self.ana).exists())
        with override_settings(MODERATION_REPORTS_PER_DAY=1):
            cache.clear()
            others = list(Message.objects.filter(sender=self.ana).exclude(pk=self.bad.pk)[:2])
            self.assertEqual(self._report(self.bo, others[0].pk).status_code, 201)
            self.assertEqual(self._report(self.bo, others[1].pk).status_code, 429)

    def test_removed_messages_cant_be_reported_but_reports_survive_deletion(self):
        self._report(self.bo, self.bad.pk)
        self.ana.delete()
        report = Report.objects.get()
        self.assertIsNone(report.reported_user)
        rows, _ = mod.reveal(moderator(), report)
        self.assertIn("the reported one", [r["text"] for r in rows])               # snapshot kept
        removed = Message.objects.filter(removed=True).first()
        self.assertEqual(self._report(self.bo, removed.pk).status_code, 400)

    def test_received_messages_offer_report_own_dont(self):
        self.client.force_login(self.bo)
        rows = self.client.get(reverse("messaging:api_poll", args=[self.conversation.public_id])).json()["messages"]
        self.assertEqual({(r["sender"], r["can_report"]) for r in rows}, {("ana", True), ("bo", False)})
        self._report(self.bo, self.bad.pk)
        rows = self.client.get(reverse("messaging:api_poll", args=[self.conversation.public_id])).json()["messages"]
        self.assertEqual([r["text"] for r in rows if r["reported"]], ["the reported one"])
        page = self.client.get(reverse("messaging:conversation", args=[self.conversation.public_id]))
        self.assertContains(page, "Also block")
        for value in ("harassment", "hate", "threats", "spam", "sexual", "other"):
            self.assertContains(page, f'value="{value}"')


class PanelTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ana, self.bo = member("ana"), member("bo")
        self.mo = moderator()
        conversation, _ = msg.start(self.ana, "bo", "hi")
        msg.accept(self.bo, conversation)
        self.bad = msg.send(self.ana, conversation, "private words here")
        self.report, _ = mod.report(self.bo, self.bad.pk, "threats")

    def test_moderators_reach_only_moderation(self):
        from dashboard import ops_urls
        from practice.studio import urls as studio_urls
        self.client.force_login(self.mo)
        self.assertEqual(self.client.get(reverse("moderation:queue")).status_code, 200)
        for pattern in ops_urls.urlpatterns + studio_urls.urlpatterns:
            if isinstance(pattern, URLPattern) and pattern.name and not pattern.pattern.converters:
                ns = "ops" if pattern in ops_urls.urlpatterns else "studio"
                url = reverse(f"{ns}:{pattern.name}")
                self.assertEqual(self.client.get(url).status_code, 403, url)
        page = self.client.get(reverse("moderation:queue")).content.decode()
        self.assertIn(f'href="{reverse("moderation:queue")}"', page)
        self.assertNotIn(f'href="{reverse("studio:list")}"', page)
        self.assertNotIn(f'href="{reverse("ops:students")}"', page)

    def test_everyone_else_gets_403(self):
        editor = member("ed", is_staff=True)
        editor.groups.add(Group.objects.get(name="Content Editor"))
        urls = [reverse("moderation:queue"), reverse("moderation:report", args=[self.report.pk]),
                reverse("moderation:restrictions"), reverse("moderation:log")]
        for user in (self.ana, member("plainstaff", is_staff=True), editor):
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 403, (user.username, url))
            self.assertEqual(self.client.post(reverse("moderation:reveal", args=[self.report.pk])).status_code, 403)
        self.assertFalse(ModerationLog.objects.exists())

    def test_content_shows_only_after_a_logged_reveal(self):
        self.client.force_login(self.mo)
        detail = self.client.get(reverse("moderation:report", args=[self.report.pk]))
        self.assertNotContains(detail, "private words")
        self.assertContains(detail, "Show reported message")
        self.assertFalse(ModerationLog.objects.exists())
        for expected in (1, 2):
            shown = self.client.post(reverse("moderation:reveal", args=[self.report.pk]))
            self.assertContains(shown, "private words here")
            self.assertEqual(shown["Cache-Control"], "no-store")
            self.assertEqual(ModerationLog.objects.filter(action="view").count(), expected)
        entry = ModerationLog.objects.filter(action="view").first()
        self.assertEqual((entry.actor, entry.subject, entry.report), (self.mo, self.ana, self.report))
        self.assertEqual(self.client.get(reverse("moderation:report", args=[self.report.pk])).status_code, 200)
        self.assertContains(self.client.get(reverse("moderation:log")), "Viewed reported content")

    def test_revealed_content_is_escaped(self):
        conversation = self.bad.conversation
        nasty = msg.send(self.ana, conversation, '<script>alert("x")</script>\nline two')
        report, _ = mod.report(self.bo, nasty.pk, "other")
        self.client.force_login(self.mo)
        shown = self.client.post(reverse("moderation:reveal", args=[report.pk])).content.decode()
        self.assertNotIn('<script>alert("x")</script>', shown)
        self.assertIn("&lt;script&gt;", shown)

    def test_no_self_moderation(self):
        # A report the moderator filed, and one about the moderator.
        conv, _ = msg.start(self.mo, "ana", "hello from mo")
        msg.accept(self.ana, conv)
        about_mo = msg.send(self.mo, conv, "mo says something")
        by_mo_msg = msg.send(self.ana, conv, "ana says something")
        filed_by_mo, _ = mod.report(self.mo, by_mo_msg.pk, "spam")
        about_mo_report, _ = mod.report(self.ana, about_mo.pk, "hate")
        self.client.force_login(self.mo)
        queue = self.client.get(reverse("moderation:queue")).context["page"].object_list
        self.assertEqual([r.pk for r in queue], [self.report.pk])
        for report in (filed_by_mo, about_mo_report):
            self.assertEqual(self.client.get(reverse("moderation:report", args=[report.pk])).status_code, 404)
            self.assertEqual(self.client.post(reverse("moderation:reveal", args=[report.pk])).status_code, 404)
            self.client.post(reverse("moderation:act", args=[report.pk]), {"action": "suspend", "reason": "x"})
            with self.assertRaises(Denied):
                mod.act(self.mo, report, "dismiss", "mine")
            with self.assertRaises(Denied):
                mod.reveal(self.mo, report)
        self.assertFalse(Restriction.objects.exists())
        self.assertFalse(ModerationLog.objects.exists())


class ActionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ana, self.bo = member("ana"), member("bo")
        self.mo = moderator()
        self.conversation, _ = msg.start(self.ana, "bo", "hi")
        msg.accept(self.bo, self.conversation)

    def _report(self, text="bad"):
        bad = msg.send(self.ana, self.conversation, text)
        report, _ = mod.report(self.bo, bad.pk, "harassment")
        return report

    def _act(self, report, action, reason="Repeated insults"):
        self.client.force_login(self.mo)
        return self.client.post(reverse("moderation:act", args=[report.pk]), {"action": action, "reason": reason})

    def test_every_action_needs_a_reason_and_is_logged(self):
        report = self._report()
        self._act(report, "warn", reason="  ")
        report.refresh_from_db()
        self.assertEqual(report.status, "open")
        actions = ("dismiss", "warn", "mute_24h", "mute_7d", "suspend")
        reports = {action: self._report(action) for action in actions}      # before ana gets muted
        for action in actions:
            report = reports[action]
            self.assertEqual(self._act(report, action).status_code, 302)
            report.refresh_from_db()
            self.assertEqual((report.status, report.resolution, report.resolved_by), ("resolved", action, self.mo))
            entry = ModerationLog.objects.get(report=report)
            self.assertEqual((entry.action, entry.reason, entry.actor, entry.subject),
                             (action, "Repeated insults", self.mo, self.ana))
        kinds = list(Restriction.objects.order_by("starts_at", "pk").values_list("kind", flat=True))
        self.assertEqual(kinds, ["warning", "mute", "mute", "suspension"])          # dismiss adds none
        self.assertEqual(Notification.objects.filter(user=self.ana).count(), 4)
        resolved_again = self._act(report, "dismiss")
        self.assertEqual(ModerationLog.objects.filter(report=report).count(), 1)     # already resolved
        self.assertEqual(resolved_again.status_code, 302)

    def test_muted_users_cant_send_and_mutes_expire(self):
        self._act(self._report(), "mute_24h")
        with self.assertRaises(Denied) as caught:
            msg.send(self.ana, self.conversation, "let me talk")
        self.assertIn("muted until", str(caught.exception))
        self.assertIn("Repeated insults", str(caught.exception))
        msg.send(self.bo, self.conversation, "bo is not muted")
        before = Message.objects.filter(sender=self.ana).count()
        later = timezone.now() + timedelta(hours=24, minutes=1)
        with mock.patch("django.utils.timezone.now", return_value=later):     # no job needed: it just ends
            self.assertEqual(mod.restriction_reason(self.ana), "")
            msg.send(self.ana, self.conversation, "I'm back")
        self.assertEqual(Message.objects.filter(sender=self.ana).count(), before + 1)

    def test_suspension_lasts_until_lifted_and_lifting_is_logged(self):
        self._act(self._report(), "suspend")
        far = timezone.now() + timedelta(days=365)
        with mock.patch("django.utils.timezone.now", return_value=far):
            self.assertIn("suspended", mod.restriction_reason(self.ana))
        restriction = Restriction.objects.get(kind="suspension")
        self.client.force_login(self.mo)
        self.client.post(reverse("moderation:lift", args=[restriction.pk]), {"reason": ""})
        self.assertIn("suspended", mod.restriction_reason(self.ana))
        self.client.post(reverse("moderation:lift", args=[restriction.pk]), {"reason": "Appeal accepted"})
        self.assertEqual(mod.restriction_reason(self.ana), "")
        self.assertEqual(ModerationLog.objects.filter(action="lift").get().reason, "Appeal accepted")
        msg.send(self.ana, self.conversation, "thanks")

    def test_users_see_their_notices_with_reason_and_support_link(self):
        self._act(self._report(), "mute_7d", reason="Threatening language")
        self.client.force_login(self.ana)
        notices = self.client.get(reverse("moderation_public:notices"))
        self.assertContains(notices, "Threatening language")
        self.assertContains(notices, reverse("pages:contact"))
        inbox = self.client.get(reverse("messaging:inbox"))
        self.assertContains(inbox, "muted until")
        self.assertContains(inbox, "Contact support")
        self.assertEqual(Notification.objects.get(user=self.ana).link_url, reverse("moderation_public:notices"))


class LogAndRetentionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ana, self.bo = member("ana"), member("bo")
        self.mo = moderator()
        conversation, _ = msg.start(self.ana, "bo", "hi")
        msg.accept(self.bo, conversation)
        self.bad = msg.send(self.ana, conversation, "bad words")
        self.report, _ = mod.report(self.bo, self.bad.pk, "hate")

    def test_log_is_append_only(self):
        mod.act(self.mo, self.report, "warn", "Be kind")
        entry = ModerationLog.objects.get()
        entry.reason = "edited"
        with self.assertRaises(AppendOnly):
            entry.save()
        with self.assertRaises(AppendOnly):
            entry.delete()
        with self.assertRaises(AppendOnly):
            ModerationLog.objects.all().delete()
        self.assertEqual(ModerationLog.objects.get().reason, "Be kind")

    def test_deleting_an_account_keeps_log_entries_anonymised(self):
        mod.act(self.mo, self.report, "warn", "Be kind")
        self.ana.delete()
        entry = ModerationLog.objects.get()
        self.assertIsNone(entry.subject)
        self.assertEqual((entry.action, entry.actor), ("warn", self.mo))

    def test_resolved_reports_go_after_180_days_and_the_log_is_anonymised(self):
        from accounts.retention import run_all
        mod.reveal(self.mo, self.report)
        mod.act(self.mo, self.report, "dismiss", "Not abusive: a quote from the course")
        open_report, _ = mod.report(self.ana, msg.send(self.bo, self.bad.conversation, "reply").pk, "spam")
        FlagEvent.objects.create(user=self.ana, kind="warned", created_at=timezone.now() - timedelta(days=91))
        later = timezone.now() + timedelta(days=181)
        FlagEvent.objects.create(user=self.ana, kind="warned", created_at=later - timedelta(days=1))
        with mock.patch("django.utils.timezone.now", return_value=later):
            self.assertEqual(mod.purge_old(dry_run=True), {"reports": 1, "flags": 1})
        self.assertIn("resolved_reports_older_than_180_days", run_all(dry_run=True))   # the daily job runs it
        counts = mod.purge_old(now=later)
        self.assertEqual(counts["reports"], 1)
        self.assertEqual(list(Report.objects.values_list("pk", flat=True)), [open_report.pk])
        self.assertEqual(set(ModerationLog.objects.values_list("action", "reason", "report")),
                         {("view", "", None), ("dismiss", "", None)})
        self.assertEqual(FlagEvent.objects.count(), 1)

    def test_retention_and_privacy_policy_say_when_moderators_read_messages(self):
        from accounts.retention import RETENTION
        text = " ".join(" ".join(row) for row in RETENTION)
        for needle in ("Reports you file", "180 days", "Moderation log", "may be offensive"):
            self.assertIn(needle, text)
        self.client.force_login(self.ana)
        policy = self.client.get(reverse("pages:privacy"))
        self.assertContains(policy, "only when someone in the conversation reports a message")
        self.assertContains(policy, "we record who opened it and when")

    def test_export_has_filed_reports_restrictions_and_warnings_but_not_reports_about_you(self):
        from accounts.privacy import build_export
        mod.act(self.mo, self.report, "warn", "Be kind")
        FlagEvent.objects.create(user=self.ana, kind="sent_anyway")
        ana_data = build_export(self.ana)
        self.assertEqual(ana_data["reports_filed"], [])                           # reporter stays anonymous
        self.assertEqual([r["reason"] for r in ana_data["messaging_restrictions"]], ["Be kind"])
        self.assertEqual([w["kind"] for w in ana_data["message_warnings"]], ["sent_anyway"])
        bo_data = build_export(self.bo)
        self.assertEqual([(r["reason"], r["status"]) for r in bo_data["reports_filed"]], [("hate", "resolved")])
        self.assertNotIn("bad words", json.dumps(bo_data["reports_filed"], default=str))   # no snapshot text
