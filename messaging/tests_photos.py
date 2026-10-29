"""Messaging v2, step 3: view-once photos.

Upload validation, encryption at rest in private storage, participant-only and recipient-only
opening, exactly one successful open (also when two opens race), no-store responses, file
deletion, expiry, blocks, reports keeping a copy, account deletion and key rotation."""

from io import BytesIO, StringIO
from pathlib import Path
from unittest import mock

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from messaging import crypto, expiry, photos, services
from messaging.models import Message
from messaging.policy import Denied, RateLimited
from moderation import services as moderation
from moderation.models import Report

User = get_user_model()


def member(name, **extra):
    return User.objects.create_user(email=f"{name}@example.com", password="testpass123", username=name, **extra)


def picture(fmt="JPEG", size=(40, 30), exif=True):
    buffer = BytesIO()
    kwargs = {}
    if exif:
        data = Image.Exif()
        data[0x010F] = "SecretCam Inc"
        data[0x8825] = {2: (23.0, 45.0, 1.0)}          # GPS latitude
        kwargs["exif"] = data.tobytes()
    Image.new("RGB", size, (10, 120, 200)).save(buffer, fmt, **kwargs)
    return buffer.getvalue()


def upload(data=None, name="my-house-gps.jpg", content_type="image/jpeg"):
    return SimpleUploadedFile(name, picture() if data is None else data, content_type=content_type)


class PhotoTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.ana, self.bo, self.cy = member("ana"), member("bo"), member("cy")
        self.conversation, _ = services.start(self.ana, "bo", "hello")
        services.accept(self.bo, self.conversation)
        self.conversation.refresh_from_db()
        self.storage = Message._meta.get_field("photo").storage

    def send(self, user=None, data=None, name="my-house-gps.jpg"):
        self.client.force_login(user or self.ana)
        return self.client.post(reverse("messaging:api_photo", args=[self.conversation.public_id]),
                                {"photo": upload(data, name)})

    def open(self, user, message_id):
        self.client.force_login(user)
        return self.client.post(reverse("messaging:api_photo_open", args=[self.conversation.public_id, message_id]))


class UploadTests(PhotoTestCase):
    def test_stored_encrypted_without_metadata_in_private_storage(self):
        res = self.send()
        self.assertEqual(res.status_code, 201)
        body = res.json()["message"]
        self.assertEqual(body["kind"], "photo")
        self.assertEqual(body["photo"], {"state": "view_once", "can_open": False})   # the sender can't open it
        self.assertNotIn("url", str(body).lower())
        message = Message.objects.get(pk=body["id"])
        path = Path(self.storage.path(message.photo.name))
        self.assertTrue(path.is_relative_to(Path(settings.PRIVATE_MEDIA_ROOT)))
        self.assertFalse(path.is_relative_to(Path(settings.MEDIA_ROOT)))
        self.assertNotIn("my-house", message.photo.name)                   # random name
        raw = path.read_bytes()
        self.assertFalse(raw.startswith(b"\xff\xd8"))                       # not a JPEG on disk
        self.assertNotIn(b"SecretCam", raw)
        with Image.open(BytesIO(crypto.decrypt_bytes(raw))) as stored:      # decrypts to a clean JPEG
            self.assertEqual(stored.format, "JPEG")
            self.assertEqual(dict(stored.getexif()), {})
        with self.assertRaises(Exception):
            Fernet(Fernet.generate_key()).decrypt(raw)                      # useless without our key
        with self.assertRaises(ValueError):
            self.storage.url(message.photo.name)                            # no URL exists

    def test_bad_files_are_refused(self):
        gif = BytesIO()
        Image.new("RGB", (4, 4)).save(gif, "GIF")
        before = set(Path(settings.PRIVATE_MEDIA_ROOT).rglob("*.bin"))
        for data in (b"<?php echo 1; ?>", gif.getvalue(), picture()[:60], b"\xff\xd8" + b"0" * (5 * 1024 * 1024 + 1)):
            res = self.send(data=data)
            self.assertEqual(res.status_code, 400, res.content)
        self.client.force_login(self.ana)
        self.assertEqual(self.client.post(reverse("messaging:api_photo", args=[self.conversation.public_id])).status_code, 400)
        self.assertFalse(Message.objects.filter(kind=Message.PHOTO).exists())
        self.assertEqual(set(Path(settings.PRIVATE_MEDIA_ROOT).rglob("*.bin")), before)   # nothing stored

    def test_requests_blocks_outsiders_and_the_daily_limit(self):
        request, _ = services.start(self.cy, "ana", "hi")
        with self.assertRaises(Denied):                                     # not accepted yet
            photos.send_photo(self.cy, request, upload())
        self.client.force_login(self.cy)
        self.assertEqual(self.client.post(reverse("messaging:api_photo", args=[self.conversation.public_id]),
                                          {"photo": upload()}).status_code, 404)
        services.block(self.bo, self.ana)
        self.assertEqual(self.send().status_code, 400)
        services.unblock(self.bo, self.ana)
        with self.settings(MESSAGING_PHOTOS_PER_DAY=2):
            photos.send_photo(self.ana, self.conversation, upload())
            photos.send_photo(self.ana, self.conversation, upload())
            with self.assertRaises(RateLimited):
                photos.send_photo(self.ana, self.conversation, upload())

    def test_get_is_not_allowed(self):
        self.client.force_login(self.ana)
        self.assertEqual(self.client.get(reverse("messaging:api_photo", args=[self.conversation.public_id])).status_code, 405)


class OpenTests(PhotoTestCase):
    def setUp(self):
        super().setUp()
        self.message = Message.objects.get(pk=self.send().json()["message"]["id"])
        self.name = self.message.photo.name

    def test_the_recipient_opens_it_once_then_it_is_gone(self):
        res = self.open(self.bo, self.message.pk)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "image/jpeg")
        self.assertIn("no-store", res["Cache-Control"])
        self.assertEqual(res["X-Content-Type-Options"], "nosniff")
        with Image.open(BytesIO(res.content)) as shown:
            self.assertEqual(dict(shown.getexif()), {})
        self.assertFalse(self.storage.exists(self.name))                    # deleted in the same request
        self.message.refresh_from_db()
        self.assertIsNotNone(self.message.photo_opened_at)
        self.assertEqual(self.message.photo.name, "")
        self.assertEqual(self.open(self.bo, self.message.pk).status_code, 410)   # a second open fails
        rows = {m["id"]: m for m in services.messages_after(self.conversation, self.ana)}
        self.assertEqual(rows[self.message.pk]["photo"], {"state": "opened", "can_open": False})
        self.assertEqual(services.inbox(self.ana)[0]["preview"], "Photo · opened")

    def test_previews_say_sent_and_view_once(self):
        self.assertEqual(services.inbox(self.ana)[0]["preview"], "Photo · sent")
        self.assertEqual(services.inbox(self.bo)[0]["preview"], "Photo · view once")
        rows = {m["id"]: m for m in services.messages_after(self.conversation, self.bo)}
        self.assertEqual(rows[self.message.pk]["photo"], {"state": "view_once", "can_open": True})

    def test_outsiders_404_and_the_sender_cant_open(self):
        self.assertEqual(self.open(self.cy, self.message.pk).status_code, 404)
        self.assertEqual(self.open(self.ana, self.message.pk).status_code, 403)
        self.client.force_login(self.bo)
        text = services.send(self.ana, self.conversation, "not a photo")
        self.assertEqual(self.open(self.bo, text.pk).status_code, 404)
        self.assertEqual(self.open(self.bo, 999999).status_code, 404)
        self.assertTrue(self.storage.exists(self.name))
        self.message.refresh_from_db()
        self.assertIsNone(self.message.photo_opened_at)

    def test_two_simultaneous_opens_only_one_wins(self):
        """The second open runs completely inside the first one's window (after it loaded the
        row, before its conditional UPDATE). Exactly one gets the photo."""
        real_get = Message.objects.get
        results = []

        def racing_get(*args, **kwargs):
            row = real_get(*args, **kwargs)                    # first request: row says "not opened"
            if not results:
                results.append("racing")                       # set first: the inner open must not race again
                results[0] = "second:" + str(self.open(self.bo, self.message.pk).status_code)
            return row

        reads = []
        real_open = self.storage.open

        def counting_open(name, mode="rb"):
            reads.append(name)
            return real_open(name, mode)

        with mock.patch.object(Message.objects, "get", side_effect=racing_get), \
                mock.patch.object(self.storage, "open", side_effect=counting_open):
            with self.assertRaises(photos.AlreadyOpened):
                photos.open_photo(self.bo, self.conversation, self.message.pk)
        self.assertEqual(results, ["second:200"])
        self.assertEqual(len(reads), 1)                       # only the winner read the file
        self.assertFalse(self.storage.exists(self.name))

    def test_blocks_stop_opening(self):
        services.block(self.ana, self.bo)
        self.assertEqual(self.open(self.bo, self.message.pk).status_code, 403)
        self.assertTrue(self.storage.exists(self.name))

    def test_expired_photos_cant_be_opened_and_their_files_are_purged(self):
        Message.all_objects.filter(pk=self.message.pk).update(expires_at=timezone.now())
        self.assertEqual(self.open(self.bo, self.message.pk).status_code, 404)
        self.assertEqual(expiry.purge()["photo_files"], 1)
        self.assertFalse(self.storage.exists(self.name))

    def test_cleanup_removes_an_opened_photo_file_left_behind(self):
        Message.all_objects.filter(pk=self.message.pk).update(photo_opened_at=timezone.now() - timezone.timedelta(minutes=1))
        expiry.purge()
        self.assertFalse(self.storage.exists(self.name))
        self.assertEqual(Message.all_objects.get(pk=self.message.pk).photo.name, "")

    def test_deleting_the_senders_account_deletes_unopened_photos(self):
        self.ana.delete()
        self.assertFalse(self.storage.exists(self.name))

    def test_key_rotation_re_encrypts_photo_files(self):
        new = Fernet.generate_key().decode()
        with self.settings(MESSAGE_ENCRYPTION_KEYS=[new] + list(settings.MESSAGE_ENCRYPTION_KEYS)):
            call_command("rotate_message_keys", stdout=StringIO())
            name = Message.objects.get(pk=self.message.pk).photo.name
            token = Path(self.storage.path(name)).read_bytes()
            Fernet(new.encode()).decrypt(token)                 # now readable with the new key alone
            self.assertEqual(self.open(self.bo, self.message.pk).status_code, 200)


class ReportedPhotoTests(PhotoTestCase):
    def setUp(self):
        super().setUp()
        self.message = Message.objects.get(pk=self.send().json()["message"]["id"])
        self.mod = member("mod", is_staff=True)
        from django.contrib.auth.models import Group
        self.mod.groups.add(Group.objects.get(name="Moderator"))

    def test_an_unopened_reported_photo_is_kept_encrypted_after_it_expires(self):
        report, _ = moderation.report(self.bo, self.message.pk, "sexual")
        self.assertTrue(report.photo)
        stored = Path(report.photo.storage.path(report.photo.name))
        self.assertTrue(stored.is_relative_to(Path(settings.PRIVATE_MEDIA_ROOT)))
        self.assertFalse(stored.read_bytes().startswith(b"\xff\xd8"))       # encrypted
        Message.all_objects.filter(pk=self.message.pk).update(expires_at=timezone.now())
        expiry.purge()
        report.refresh_from_db()
        self.assertIsNone(report.message_id)
        self.assertTrue(stored.exists())
        self.client.force_login(self.mod)
        page = self.client.get(reverse("moderation:report", args=[report.pk]))
        self.assertNotContains(page, "data:image")                          # hidden until "Show"
        shown = self.client.post(reverse("moderation:reveal", args=[report.pk]))
        self.assertContains(shown, 'src="data:image/jpeg;base64,')
        self.assertContains(shown, "[View-once photo: copy attached]")
        self.assertIn("no-store", shown["Cache-Control"])

    def test_an_opened_photo_says_so_in_the_report(self):
        self.open(self.bo, self.message.pk)
        report, _ = moderation.report(self.bo, self.message.pk, "sexual")
        self.assertFalse(report.photo)
        rows, _ = moderation.reveal(self.mod, report)
        self.assertIn("[View-once photo: already opened, so no copy exists]", [r["text"] for r in rows])

    def test_report_photos_are_deleted_with_the_report(self):
        report, _ = moderation.report(self.bo, self.message.pk, "spam")
        name = report.photo.name
        Report.objects.filter(pk=report.pk).update(status=Report.RESOLVED,
                                                   resolved_at=timezone.now() - timezone.timedelta(days=200))
        moderation.purge_old()
        self.assertFalse(Report.objects.filter(pk=report.pk).exists())
        self.assertFalse(report.photo.storage.exists(name))
