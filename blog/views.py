"""Public blog pages, the private draft preview, and post images.

Everything public reads `Post.objects.published()`. Drafts, their preview links and their
images answer 404 to anyone who can't manage the blog, so they don't reveal that a draft exists.
"""

from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from cyberquest.media_access import serve_stored_file

from .access import can_manage_blog
from .models import Post, PostImage
from .rendering import safe_html

PER_PAGE = 9


def post_list(request):
    posts = Post.objects.published().select_related("cover", "author").order_by("-published_at", "-pk")
    page = Paginator(posts, PER_PAGE).get_page(request.GET.get("page") or 1)
    return render(request, "blog/list.html", {"page": page})


def _detail(request, post, preview=False):
    cover = post.cover
    og_image = request.build_absolute_uri(f"/blog/img/{cover.public_id}/") if cover else ""
    return render(request, "blog/detail.html", {
        "post": post, "body": safe_html(post.body_html), "preview": preview,
        "canonical": request.build_absolute_uri(f"/blog/{post.slug}/"), "og_image": og_image,
    })


def post_detail(request, slug):
    post = get_object_or_404(Post.objects.published().select_related("cover", "author"), slug=slug)
    return _detail(request, post)


def preview(request, token):
    """A draft (or published) post for the people who can edit it; 404 for everyone else."""
    if not can_manage_blog(request.user):
        raise Http404("Post not found.")
    post = get_object_or_404(Post.objects.select_related("cover", "author"), preview_token=token)
    response = _detail(request, post, preview=True)
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Cache-Control"] = "private, no-store"
    return response


def image(request, public_id, variant="full"):
    picture = get_object_or_404(PostImage.objects.select_related("post"), public_id=public_id)
    visible = Post.objects.published().filter(pk=picture.post_id).exists()
    if not visible and not can_manage_blog(request.user):
        raise Http404("Image not found.")
    response = serve_stored_file(picture.thumbnail if variant == "thumb" else picture.image)
    if response is None:
        raise Http404("Image not found.")
    if visible:
        response["Cache-Control"] = "public, max-age=86400"
    return response
