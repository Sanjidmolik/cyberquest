from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden


def can_use_studio(user):
    return bool(user.is_authenticated and (user.is_superuser or (user.is_staff and user.has_perm("practice.use_studio"))))


def studio_required(*perms):
    """Server-side gate for every Practice Studio view: staff with the studio permission plus
    any `perms` given (e.g. "practice.publish_scenario"). Superusers pass; everyone else gets 403."""

    def decorator(view):
        @login_required(login_url="/admin-login/")
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            user = request.user
            if not can_use_studio(user) or not all(user.has_perm(p) for p in perms):
                return HttpResponseForbidden("The Practice Studio needs a Content Editor or Content Publisher account.")
            return view(request, *args, **kwargs)

        return wrapped

    return decorator
