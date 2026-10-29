from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden


def can_moderate(user):
    return bool(user.is_authenticated and (user.is_superuser or (user.is_staff and user.has_perm("moderation.moderate"))))


def moderator_required(view):
    """Server-side gate for every moderation page: staff in the Moderator group (or superusers)."""

    @login_required(login_url="/admin-login/")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not can_moderate(request.user):
            return HttpResponseForbidden("Moderation needs a Moderator account.")
        return view(request, *args, **kwargs)

    return wrapped
