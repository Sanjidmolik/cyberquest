"""Wizard step 3: preview the latest SAVED draft in the real student player.

- Staff with Studio access only. Everyone else (students, other staff, signed-out visitors)
  gets 404, so preview URLs reveal nothing. Both pages are noindex and not cached.
- The play page is the only page on the site that may be framed, and only by this site:
  X-Frame-Options SAMEORIGIN and CSP `frame-ancestors 'self'`. Everything else stays DENY.
- Preview attempts award no XP or badges and never reach stats (practice/session_views.py).
"""

from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin

from ..models import Scenario
from ..session_views import render_session
from . import editor
from .access import can_use_studio
from .preview import answer_key
from .services import working_content


def _preview_scenario(request, slug):
    if not can_use_studio(request.user):
        raise Http404("Not found.")
    return get_object_or_404(Scenario.objects.select_related("topic", "draft_saved_by"), slug=slug)


def _private(response):
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Cache-Control"] = "private, no-store"
    return response


def wizard_preview(request, slug):
    from .views import _shell
    from courses.models import Course
    scenario = _preview_scenario(request, slug)
    content = working_content(scenario)
    return _private(render(request, "practice/studio/wizard_preview.html", _shell(
        request, "Preview", scenario=scenario, wizard_step=3, xp=editor.XP_REWARD,
        topics=Course.objects.none(), answer_key=answer_key(content),
        play_url=reverse("studio:play", args=[scenario.slug]),
    )))


@xframe_options_sameorigin
def play(request, slug):
    scenario = _preview_scenario(request, slug)
    title = editor.working_meta(scenario)["title"] or scenario.title
    response = render_session(request, scenario, content=working_content(scenario), title=title,
                              preview_url=reverse("studio:play", args=[scenario.slug]))
    response["Content-Security-Policy"] = "frame-ancestors 'self'"
    return _private(response)
