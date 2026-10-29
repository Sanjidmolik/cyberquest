"""Blog: permissions, drafts hidden everywhere, slug stability, the sanitiser, image upload
validation and metadata stripping, and the public pages."""

import re
import shutil
import tempfile
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import URLPattern, reverse
from django.utils import timezone
from PIL import Image

from . import images, rendering, services
from . import panel_urls
from .models import Post, PostImage

User = get_user_model()
MEDIA = tempfile.mkdtemp()


def member(name, group=None, **extra):
    user = User.objects.create_user(email=f"{name}@example.com", password="testpass123", username=name, **extra)
    if group:
        user.groups.add(Group.objects.get(name=group))
    return User.objects.get(pk=user.pk)


def picture_bytes(fmt="JPEG", size=(32, 20), exif=False):
    buffer = BytesIO()
    img = Image.new("RGB", size, (200, 30, 90))
    kwargs = {}
    if exif:
        data = Image.Exif()
        data[0x010F] = "SecretCam Inc"        # Make
        data[0x8825] = {2: (23.0, 45.0, 1.0)}  # GPS IFD: latitude
        kwargs["exif"] = data.tobytes()
    img.save(buffer, fmt, **kwargs)
    return buffer.getvalue()


def upload(name="photo.jpg", data=None, content_type="image/jpeg"):
    return SimpleUploadedFile(name, data if data is not None else picture_bytes(), content_type=content_type)


def make_post(author, title="Spot a phishing email", status="draft", body="Look at the **sender**.", **extra):
    post = Post.objects.create(title=title, slug=extra.pop("slug", None) or title.lower().replace(" ", "-"),
                               excerpt=f"About {title}", body=body, body_html=rendering.render(body),
                               author=author, **extra)
    if status == "published":
        services.publish(post)
    return post


@override_settings(MEDIA_ROOT=MEDIA)
class BlogTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.publisher = member("pub", "Content Publisher", is_staff=True)
        self.root = User.objects.create_superuser(email="root@example.com", password="testpass123", username="root")
        self.student = member("student")


class PermissionTests(BlogTestCase):
    def _editor_urls(self, post, picture):
        values = {"pk": post.pk, "public_id": picture.public_id}
        for pattern in panel_urls.urlpatterns:
            if isinstance(pattern, URLPattern):
                yield reverse(f"blog_panel:{pattern.name}", kwargs={k: values[k] for k in pattern.pattern.converters})

    def test_only_publishers_and_superusers_reach_the_editor(self):
        post = make_post(self.publisher)
        picture = services.add_image(post, upload(), "A red square", self.publisher)
        editor = member("ed", "Content Editor", is_staff=True)
        mod = member("mo", "Moderator", is_staff=True)
        for user in (self.student, editor, mod, member("staffer", is_staff=True)):
            self.client.force_login(user)
            for url in self._editor_urls(post, picture):
                self.assertEqual(self.client.get(url).status_code, 403, (user.username, url))
                self.assertEqual(self.client.post(url, {"action": "delete"}).status_code, 403, (user.username, url))
        self.assertTrue(PostImage.objects.filter(pk=picture.pk).exists())
        for user in (self.publisher, self.root):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("blog_panel:list")).status_code, 200)
            self.assertEqual(self.client.get(reverse("blog_panel:edit", args=[post.pk])).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("blog_panel:list")).status_code, 302)

    def test_nav_shows_blog_to_publishers_only(self):
        self.client.force_login(self.publisher)
        page = self.client.get(reverse("blog_panel:list")).content.decode()
        self.assertIn(f'href="{reverse("blog_panel:list")}"', page)
        self.assertIn(f'href="{reverse("studio:list")}"', page)              # publishers also have the Studio
        self.assertNotIn(f'href="{reverse("ops:students")}"', page)
        self.client.force_login(member("ed2", "Content Editor", is_staff=True))
        self.assertNotIn(f'href="{reverse("blog_panel:list")}"', self.client.get(reverse("studio:list")).content.decode())

    def test_publishers_sign_in_to_the_blog(self):
        login = self.client.post(f"{reverse('admin_login')}?next={reverse('blog_panel:list')}",
                                 {"email": "pub@example.com", "password": "testpass123"})
        self.assertRedirects(login, reverse("blog_panel:list"))

    def test_create_edit_publish_flow(self):
        self.client.force_login(self.publisher)
        res = self.client.post(reverse("blog_panel:new"), {"title": "Two-factor basics", "slug": "",
                                                           "excerpt": "Why codes matter.", "body": "## Why\nBecause."})
        post = Post.objects.get()
        self.assertRedirects(res, reverse("blog_panel:edit", args=[post.pk]))
        self.assertEqual((post.slug, post.status, post.author), ("two-factor-basics", "draft", self.publisher))
        self.assertIn("<h2>Why</h2>", post.body_html)
        self.client.post(reverse("blog_panel:publish", args=[post.pk]), {"action": "publish"})
        post.refresh_from_db()
        self.assertEqual(post.status, "published")
        self.assertEqual(self.client.get(reverse("blog:detail", args=[post.slug])).status_code, 200)


class DraftHidingTests(BlogTestCase):
    def setUp(self):
        super().setUp()
        self.draft = make_post(self.publisher, title="Secret draft", body="Not ready yet")
        self.live = make_post(self.publisher, title="Public post", status="published")
        self.draft_image = services.add_image(self.draft, upload(), "Draft picture", self.publisher)

    def test_drafts_are_hidden_from_everyone_without_permission(self):
        for user in (None, self.student, member("ed", "Content Editor", is_staff=True)):
            if user:
                self.client.force_login(user)
            else:
                self.client.logout()
            listing = self.client.get(reverse("blog:list"))
            self.assertContains(listing, "Public post")
            self.assertNotContains(listing, "Secret draft")
            self.assertEqual(self.client.get(reverse("blog:detail", args=[self.draft.slug])).status_code, 404)
            self.assertEqual(self.client.get(reverse("blog:preview", args=[self.draft.preview_token])).status_code, 404)
            self.assertEqual(self.client.get(reverse("blog:image", args=[self.draft_image.public_id])).status_code, 404)
            self.assertEqual(self.client.get(reverse("blog:thumb", args=[self.draft_image.public_id])).status_code, 404)
            if user:                                      # site search needs sign-in
                found = self.client.get(reverse("pages:search"), {"q": "post"})
                self.assertContains(found, "Public post")
                self.assertNotContains(found, "Secret draft")

    def test_unpublished_posts_disappear_again(self):
        services.unpublish(self.live)
        self.assertEqual(self.client.get(reverse("blog:detail", args=[self.live.slug])).status_code, 404)

    def test_future_dated_posts_stay_hidden(self):
        Post.objects.filter(pk=self.live.pk).update(published_at=timezone.now() + timedelta(days=1))
        self.assertEqual(self.client.get(reverse("blog:detail", args=[self.live.slug])).status_code, 404)

    def test_editors_preview_drafts_privately(self):
        self.client.force_login(self.publisher)
        preview = self.client.get(reverse("blog:preview", args=[self.draft.preview_token]))
        self.assertContains(preview, "Not ready yet")
        self.assertContains(preview, "isn’t public")
        self.assertEqual(preview["X-Robots-Tag"], "noindex, nofollow")
        self.assertContains(preview, 'content="noindex, nofollow"')
        self.assertEqual(self.client.get(reverse("blog:image", args=[self.draft_image.public_id])).status_code, 200)
        self.assertEqual(self.client.get(reverse("blog:preview", args=["guess"])).status_code, 404)


class SlugTests(BlogTestCase):
    def test_slug_is_fixed_once_published(self):
        self.client.force_login(self.publisher)
        post = make_post(self.publisher, title="Old title")
        self.client.post(reverse("blog_panel:edit", args=[post.pk]),
                         {"title": "Old title", "slug": "draft-slug", "excerpt": "x", "body": "y"})
        post.refresh_from_db()
        self.assertEqual(post.slug, "draft-slug")                                 # free while a draft
        services.publish(post)
        self.client.post(reverse("blog_panel:edit", args=[post.pk]),
                         {"title": "A completely new title", "slug": "hijacked", "excerpt": "x", "body": "y"})
        post.refresh_from_db()
        self.assertEqual((post.title, post.slug), ("A completely new title", "draft-slug"))
        services.unpublish(post)
        services.publish(post)
        post.refresh_from_db()
        self.assertEqual(post.slug, "draft-slug")
        self.assertEqual(self.client.get("/blog/draft-slug/").status_code, 200)

    def test_new_slugs_are_unique(self):
        self.client.force_login(self.publisher)
        for _ in range(2):
            self.client.post(reverse("blog_panel:new"), {"title": "Same title", "excerpt": "x", "body": "y"})
        self.assertEqual(sorted(Post.objects.values_list("slug", flat=True)), ["same-title", "same-title-2"])


class SanitiserTests(BlogTestCase):
    def test_dangerous_html_never_survives(self):
        cases = [
            '<script>alert(1)</script>',
            '<img src="/blog/img/x/" onerror="alert(1)">',
            '<iframe src="https://evil.example"></iframe>',
            '<style>body{display:none}</style>',
            '<a href="javascript:alert(1)">click</a>',
            '<div onclick="alert(1)">x</div>',
            '<svg onload="alert(1)"></svg>',
            '<form action="https://evil.example"><input name="pw"></form>',
        ]
        real_tag = re.compile(r"<(\w+)([^>]*)>")
        for raw in cases:
            for html in (rendering.render(f"Intro\n\n{raw}\n\nOutro"), rendering.sanitise(raw)):
                for tag, attrs in real_tag.findall(html):     # escaped text (&lt;...) is harmless
                    self.assertIn(tag, rendering.TAGS, raw)
                    self.assertNotRegex(attrs, r"(?i)\son\w+\s*=", raw)
                    self.assertNotIn("javascript:", attrs, raw)

    def test_raw_html_is_shown_as_text(self):
        html = rendering.render("Use <b>bold</b> carefully")
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", html)
        self.assertNotIn("<b>", html)

    def test_markdown_features_and_link_rel(self):
        html = rendering.render("# Title\n\n**b** *i* [site](https://example.com)\n\n- one\n\n`code`\n\n"
                                "[mail](mailto:a@b.co) [bad](javascript:alert(1))")
        self.assertIn("<h2>Title</h2>", html)                 # the post title is the only <h1>
        self.assertIn('rel="nofollow noopener noreferrer"', html)
        self.assertIn('href="https://example.com"', html)
        self.assertIn('href="mailto:a@b.co"', html)
        self.assertNotIn("javascript", html)
        for tag in ("<strong>", "<em>", "<li>", "<code>"):
            self.assertIn(tag, html)

    def test_only_our_own_images(self):
        html = rendering.render("![ours](/blog/img/abc/) ![tracker](https://evil.example/pixel.gif)")
        self.assertIn('src="/blog/img/abc/"', html)
        self.assertNotIn("evil.example", html)

    def test_stored_html_is_sanitised_again_when_shown(self):
        post = make_post(self.publisher, title="Tampered", status="published")
        Post.objects.filter(pk=post.pk).update(body_html='<p>ok</p><script>alert(1)</script>')
        page = self.client.get(reverse("blog:detail", args=[post.slug]))
        self.assertNotContains(page, "<script>alert(1)")
        self.assertContains(page, "<p>ok</p>")


class UploadTests(BlogTestCase):
    def setUp(self):
        super().setUp()
        self.post = make_post(self.publisher)

    def test_valid_jpeg_png_webp_are_accepted(self):
        for fmt, name in (("JPEG", "a.jpg"), ("PNG", "b.png"), ("WEBP", "c.webp")):
            picture = services.add_image(self.post, upload(name, picture_bytes(fmt)), "Alt", self.publisher)
            with Image.open(picture.image.path) as stored:
                self.assertEqual(stored.format, fmt)

    def test_fake_images_wrong_formats_and_big_files_are_rejected(self):
        gif = BytesIO()
        Image.new("RGB", (4, 4)).save(gif, "GIF")
        cases = [
            upload("evil.jpg", b"<?php echo 'hi'; ?>"),                       # not an image at all
            upload("truncated.png", picture_bytes("PNG")[:40], "image/png"),  # broken image
            upload("anim.jpg", gif.getvalue()),                               # GIF named .jpg
            upload("huge.jpg", b"\xff\xd8" + b"0" * (5 * 1024 * 1024 + 1)),   # over 5 MB
        ]
        for case in cases:
            with self.assertRaises(ValidationError, msg=case.name):
                services.add_image(self.post, case, "Alt", self.publisher)
        self.assertFalse(PostImage.objects.exists())

    def test_upload_page_requires_alt_text(self):
        self.client.force_login(self.publisher)
        self.client.post(reverse("blog_panel:image_upload", args=[self.post.pk]), {"file": upload(), "alt": "  "})
        self.assertFalse(PostImage.objects.exists())
        self.client.post(reverse("blog_panel:image_upload", args=[self.post.pk]),
                         {"file": upload(), "alt": "Phishing email example", "make_cover": "on"})
        picture = PostImage.objects.get()
        self.post.refresh_from_db()
        self.assertEqual((picture.alt, self.post.cover), ("Phishing email example", picture))

    def test_metadata_is_stripped_and_images_resized_with_random_names(self):
        data = picture_bytes("JPEG", size=(3000, 1500), exif=True)
        with Image.open(BytesIO(data)) as original:
            self.assertIn(0x010F, original.getexif())                         # the test file has EXIF
        picture = services.add_image(self.post, upload("my-home-address.jpg", data), "Wide", self.publisher)
        with Image.open(picture.image.path) as stored:
            self.assertEqual(stored.size, (1600, 800))
            self.assertEqual(dict(stored.getexif()), {})
            self.assertNotIn("exif", stored.info)
        with Image.open(picture.thumbnail.path) as thumb:
            self.assertEqual(thumb.size, (640, 320))
            self.assertEqual(dict(thumb.getexif()), {})
        self.assertNotIn("my-home-address", picture.image.name)
        self.assertEqual((picture.width, picture.height), (1600, 800))

    def test_decompression_bombs_are_refused(self):
        with self.assertRaises(ValidationError):
            images.process(upload("bomb.png", picture_bytes("PNG", size=(8000, 6000)), "image/png"))


class InsertImageTests(BlogTestCase):
    """The editor's "Insert image" button: same validation as the Images panel, JSON answer."""

    def setUp(self):
        super().setUp()
        self.post = make_post(self.publisher)
        self.url = reverse("blog_panel:image_insert", args=[self.post.pk])

    def test_returns_the_markdown_line_for_the_cursor(self):
        self.client.force_login(self.publisher)
        data = picture_bytes("JPEG", size=(2400, 1200), exif=True)
        res = self.client.post(self.url, {"file": upload("home.jpg", data), "alt": "Fake [login] page"})
        self.assertEqual(res.status_code, 201)
        picture = PostImage.objects.get()
        self.assertEqual(res.json()["markdown"], f"![Fake \\[login\\] page]({reverse('blog:image', args=[picture.public_id])})")
        self.assertEqual(picture.alt, "Fake [login] page")
        with Image.open(picture.image.path) as stored:                       # same processing as the panel
            self.assertEqual((stored.size, dict(stored.getexif())), ((1600, 800), {}))
        html = rendering.render("Before\n\n" + res.json()["markdown"])
        self.assertIn('alt="Fake [login] page"', html)
        self.assertIn(f'src="{reverse("blog:image", args=[picture.public_id])}"', html)
        self.assertIsNone(Post.objects.get(pk=self.post.pk).cover)

    def test_bad_files_and_missing_alt_text_are_refused(self):
        self.client.force_login(self.publisher)
        for payload in ({"file": upload("evil.jpg", b"<?php ?>"), "alt": "Alt"},
                        {"file": upload(), "alt": "   "},
                        {"alt": "No file"}):
            res = self.client.post(self.url, payload)
            self.assertEqual(res.status_code, 400)
            self.assertTrue(res.json()["errors"])
        self.assertFalse(PostImage.objects.exists())

    def test_only_blog_managers_can_insert(self):
        editor = member("ed", "Content Editor", is_staff=True)
        for user in (editor, self.student):
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.url, {"file": upload(), "alt": "x"}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {"file": upload(), "alt": "x"}).status_code, 302)
        self.client.force_login(self.publisher)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertFalse(PostImage.objects.exists())

    def test_editor_page_has_the_button_once_the_draft_exists(self):
        self.client.force_login(self.publisher)
        page = self.client.get(reverse("blog_panel:edit", args=[self.post.pk]))
        self.assertContains(page, 'id="bp-insert-open"')
        self.assertContains(page, f'action="{self.url}"')
        self.assertContains(page, "blog/js/panel-editor.js")
        new = self.client.get(reverse("blog_panel:new"))
        self.assertNotContains(new, 'id="bp-insert-open"')
        self.assertContains(new, "Save the draft first")


class PublicPageTests(BlogTestCase):
    def test_list_is_newest_first_nine_per_page(self):
        now = timezone.now()
        for n in range(11):
            post = make_post(self.publisher, title=f"Post {n:02d}", status="published")
            Post.objects.filter(pk=post.pk).update(published_at=now - timedelta(days=n))
        first = self.client.get(reverse("blog:list"))
        titles = [p.title for p in first.context["page"].object_list]
        self.assertEqual(titles, [f"Post {n:02d}" for n in range(9)])
        second = self.client.get(reverse("blog:list"), {"page": 2})
        self.assertEqual([p.title for p in second.context["page"].object_list], ["Post 09", "Post 10"])

    def test_article_shows_reading_time_author_date_and_social_tags(self):
        body = " ".join(["word"] * 600)
        post = make_post(self.publisher, title="Long read", status="published", body=body)
        cover = services.add_image(post, upload(), "Cover alt", self.publisher, make_cover=True)
        page = self.client.get(reverse("blog:detail", args=[post.slug]))
        self.assertContains(page, "3 min read")
        self.assertContains(page, "by pub")
        self.assertNotContains(page, "pub@example.com")
        self.assertContains(page, '<meta name="description" content="About Long read">')
        self.assertContains(page, '<meta property="og:title" content="Long read">')
        self.assertContains(page, '<meta property="og:type" content="article">')
        self.assertContains(page, f'content="http://testserver/blog/img/{cover.public_id}/"')
        self.assertContains(page, 'alt="Cover alt"')

    def test_titles_and_excerpts_are_escaped(self):
        post = make_post(self.publisher, title='<script>x</script>', slug="xss", status="published")
        Post.objects.filter(pk=post.pk).update(excerpt='"><script>y</script>')
        page = self.client.get(reverse("blog:detail", args=["xss"])).content.decode()
        self.assertNotIn("<script>x</script>", page)
        self.assertNotIn('"><script>y', page)
