from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden


def can_manage_blog(user):
    return bool(user.is_authenticated and (user.is_superuser or (user.is_staff and user.has_perm("blog.publish_post"))))


def blog_required(view):
    """Server-side gate for the blog editor: Content Publishers (staff) and superusers."""

    @login_required(login_url="/admin-login/")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not can_manage_blog(request.user):
            return HttpResponseForbidden("The blog editor needs a Content Publisher account.")
        return view(request, *args, **kwargs)

    return wrapped
