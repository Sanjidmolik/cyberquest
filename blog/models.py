"""Blog posts written by Content Publishers and superusers.

- Drafts are visible only to people who may manage the blog (editor, preview link, images).
  Everything public goes through `Post.objects.published()`.
- The slug can change while a post is a draft and is fixed from its first publication, so
  later title changes (or unpublishing and republishing) never break links.
- The body is Markdown; the stored HTML is produced by blog/rendering.py (raw HTML disabled,
  then sanitised with nh3).
"""

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def new_token():
    return secrets.token_urlsafe(18)


class PostQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Post.PUBLISHED, published_at__lte=timezone.now())


class Post(models.Model):
    DRAFT, PUBLISHED = "draft", "published"
    STATUSES = [(DRAFT, "Draft"), (PUBLISHED, "Published")]

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    excerpt = models.CharField(max_length=300, help_text="One or two sentences: shown in the list and in link previews.")
    body = models.TextField(help_text="Markdown.")
    body_html = models.TextField(blank=True, editable=False)
    cover = models.ForeignKey("PostImage", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    status = models.CharField(max_length=10, choices=STATUSES, default=DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    first_published_at = models.DateTimeField(null=True, blank=True, editable=False)   # locks the slug
    preview_token = models.CharField(max_length=32, unique=True, default=new_token, editable=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PostQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-created_at"]
        permissions = [("publish_post", "Can write, edit and publish blog posts")]

    def __str__(self):
        return self.title

    @property
    def slug_locked(self):
        return self.first_published_at is not None

    @property
    def reading_minutes(self):
        return max(1, round(len(self.body.split()) / 200))


class PostImage(models.Model):
    """An uploaded image, re-encoded without metadata: `image` (max 1600 px wide) and a smaller
    `thumbnail`. Served by blog.views.image only while its post is visible to the viewer."""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="images")
    public_id = models.CharField(max_length=32, unique=True, default=new_token, editable=False)
    image = models.ImageField(upload_to="blog/")
    thumbnail = models.ImageField(upload_to="blog/")
    alt = models.CharField(max_length=200, help_text="Describe the image for people who can't see it.")
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.alt

    @property
    def markdown(self):
        """The line that shows this image in a post. Brackets and line breaks in the alt text
        are escaped/flattened so they can't end the image syntax early."""
        from django.urls import reverse
        alt = " ".join(self.alt.split()).replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")
        return f"![{alt}]({reverse('blog:image', args=[self.public_id])})"
