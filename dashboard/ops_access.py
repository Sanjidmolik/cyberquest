from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden


def superuser_required(view):
    """Server-side gate. Students and non-superuser staff are refused."""

    @login_required(login_url="/accounts/login/")
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            return HttpResponseForbidden("Superuser access is required for the Admin Command Center.")
        return view(request, *args, **kwargs)

    return wrapped
