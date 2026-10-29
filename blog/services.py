from django.db import transaction
from django.utils import timezone

from . import images, rendering
from .models import Post, PostImage


def save_post(form, user):
    post = form.save(commit=False)
    if post.pk is None:
        post.author = user
    post.body_html = rendering.render(post.body)
    post.save()
    return post


def publish(post):
    now = timezone.now()
    post.status = Post.PUBLISHED
    post.published_at = post.published_at or now
    post.first_published_at = post.first_published_at or now     # from now on the slug is fixed
    post.body_html = rendering.render(post.body)
    post.save(update_fields=["status", "published_at", "first_published_at", "body_html", "updated_at"])


def unpublish(post):
    post.status = Post.DRAFT
    post.save(update_fields=["status", "updated_at"])


def add_image(post, upload, alt, user, make_cover=False):
    """Validate and re-encode an upload (raises ValidationError), store it, optionally as cover."""
    main, thumb, width, height = images.process(upload)
    with transaction.atomic():
        picture = PostImage(post=post, alt=alt, width=width, height=height, uploaded_by=user)
        picture.image.save(main.name, main, save=False)
        picture.thumbnail.save(thumb.name, thumb, save=False)
        picture.save()
        if make_cover:
            Post.objects.filter(pk=post.pk).update(cover=picture)
    return picture


def delete_image(picture):
    for field in (picture.image, picture.thumbnail):
        if field:
            field.delete(save=False)
    picture.delete()
