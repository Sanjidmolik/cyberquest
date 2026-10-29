"""The blog editor in the Admin Command Center (Content Publishers and superusers)."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import services
from .access import blog_required
from .forms import ImageForm, PostForm
from .models import Post, PostImage


def _shell(request, title, **extra):
    extra.update({"active": "blog", "page_title": title})
    if request.user.is_superuser:
        from pages.models import ContactMessage
        extra["open_contact"] = ContactMessage.objects.filter(is_resolved=False).count()
    return extra


@blog_required
def post_list(request):
    posts = Post.objects.select_related("author").order_by("-updated_at")
    return render(request, "blog/panel/list.html", _shell(request, "Blog", posts=posts))


@blog_required
def post_new(request):
    form = PostForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        post = services.save_post(form, request.user)
        messages.success(request, "Draft saved. Add images below, preview it, then publish.")
        return redirect("blog_panel:edit", pk=post.pk)
    return render(request, "blog/panel/edit.html", _shell(request, "New post", form=form, post=None))


@blog_required
def post_edit(request, pk):
    post = get_object_or_404(Post, pk=pk)
    form = PostForm(request.POST or None, instance=post)
    if request.method == "POST" and form.is_valid():
        services.save_post(form, request.user)
        messages.success(request, "Saved.")
        return redirect("blog_panel:edit", pk=post.pk)
    return render(request, "blog/panel/edit.html", _shell(
        request, post.title, form=form, post=post, image_form=ImageForm(),
        preview_url=request.build_absolute_uri(reverse("blog:preview", args=[post.preview_token])),
    ))


@blog_required
@require_POST
def post_publish(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if request.POST.get("action") == "unpublish":
        services.unpublish(post)
        messages.success(request, "Unpublished: the post is a draft again. Its address stays the same.")
    else:
        services.publish(post)
        messages.success(request, f"Published at /blog/{post.slug}/.")
    return redirect("blog_panel:edit", pk=post.pk)


@blog_required
@require_POST
def image_upload(request, pk):
    post = get_object_or_404(Post, pk=pk)
    form = ImageForm(request.POST, request.FILES)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("blog_panel:edit", pk=post.pk)
    try:
        services.add_image(post, form.cleaned_data["file"], form.cleaned_data["alt"], request.user,
                           form.cleaned_data["make_cover"])
    except ValidationError as exc:
        for error in exc.messages:
            messages.error(request, error)
    else:
        messages.success(request, "Image added. Copy its Markdown line into the post where it should appear.")
    return redirect("blog_panel:edit", pk=post.pk)


@blog_required
@require_POST
def image_insert(request, pk):
    """The editor's "Insert image" button: the same form and validation as image_upload, but
    answers with JSON so the page can put the Markdown line at the cursor."""
    post = get_object_or_404(Post, pk=pk)
    form = ImageForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse({"errors": [e for errors in form.errors.values() for e in errors]}, status=400)
    try:
        picture = services.add_image(post, form.cleaned_data["file"], form.cleaned_data["alt"], request.user)
    except ValidationError as exc:
        return JsonResponse({"errors": exc.messages}, status=400)
    return JsonResponse({"markdown": picture.markdown, "alt": picture.alt,
                         "thumb": reverse("blog:thumb", args=[picture.public_id])}, status=201)


@blog_required
@require_POST
def image_action(request, public_id):
    picture = get_object_or_404(PostImage.objects.select_related("post"), public_id=public_id)
    post = picture.post
    if request.POST.get("action") == "cover":
        Post.objects.filter(pk=post.pk).update(cover=picture)
        messages.success(request, "Cover image set.")
    elif request.POST.get("action") == "delete":
        services.delete_image(picture)
        messages.success(request, "Image deleted. Remove it from the post text too if it was used.")
    return redirect("blog_panel:edit", pk=post.pk)
