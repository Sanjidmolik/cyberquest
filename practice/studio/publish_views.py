"""Wizard step 4 pages: the checklist with Publish, and the version history.

Who may do what is checked here, on the server, for every POST:
  - any Studio user (Content Editor or Publisher) sees the checklist and the history;
  - editors who may change sessions can "Request review";
  - only Content Publishers and superusers (practice.publish_scenario) can publish,
    archive, un-archive and restore. Hiding their buttons is only a convenience.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..models import Scenario
from . import checks, editor, publishing
from .access import studio_required

PUBLISH = "practice.publish_scenario"
EDIT = "practice.change_scenario"


def _scenario(slug):
    return get_object_or_404(Scenario.objects.select_related("topic", "draft_saved_by"), slug=slug)


def _revision(request):
    try:
        return int(request.POST.get("revision", ""))
    except ValueError:
        return -1


def _conflict_message(exc):
    from .views import _when
    return f"{exc.by} changed this session{_when(exc.at)}. Check the latest version below, then try again."


@studio_required()
def wizard_check(request, slug):
    from .views import _wizard
    scenario = _scenario(slug)
    rules = checks.run(scenario)
    user = request.user
    return render(request, "practice/studio/wizard_check.html", _wizard(
        request, scenario, 4, "Check & publish", rules=rules, passed=checks.passed(rules),
        failed_count=sum(not rule["ok"] for rule in rules),
        can_publish=user.has_perm(PUBLISH), can_edit=user.has_perm(EDIT),
        has_changes=publishing.has_changes(scenario) or scenario.status == Scenario.DRAFT,
        draft_title=editor.working_meta(scenario)["title"] or scenario.title,
        versions=scenario.versions.select_related("published_by")[:3],
    ))


@studio_required(PUBLISH)
@require_POST
def publish(request, slug):
    scenario = _scenario(slug)
    try:
        row = publishing.publish(scenario.pk, request.user, revision=_revision(request))
    except editor.Conflict as exc:
        messages.error(request, _conflict_message(exc))
    except editor.EditorError as exc:                  # includes ChecksFailed
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Published version {row.version}. Students see it now.")
    return redirect("studio:check", slug=slug)


@studio_required(PUBLISH)
@require_POST
def archive(request, slug):
    try:
        publishing.archive(_scenario(slug).pk, request.user)
    except editor.EditorError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Archived. Students no longer see it in the Practice Center; their history and XP are kept.")
    return redirect("studio:check", slug=slug)


@studio_required(PUBLISH)
@require_POST
def unarchive(request, slug):
    try:
        row = publishing.unarchive(_scenario(slug).pk, request.user)
    except editor.EditorError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Un-archived: students can see it again." if row.status == Scenario.PUBLISHED
                         else "Un-archived as a draft (it was never published).")
    return redirect("studio:check", slug=slug)


@studio_required(PUBLISH)
@require_POST
def restore(request, slug, version):
    scenario = _scenario(slug)
    try:
        publishing.restore(scenario.pk, request.user, version=version, revision=_revision(request))
    except editor.Conflict as exc:
        messages.error(request, _conflict_message(exc))
        return redirect("studio:versions", slug=slug)
    except editor.EditorError as exc:
        messages.error(request, str(exc))
        return redirect("studio:versions", slug=slug)
    messages.success(request, f"Version {version} is now the draft. Students still see version {scenario.version} "
                              "until you check and publish it.")
    return redirect("studio:check", slug=slug)


@studio_required(EDIT)
@require_POST
def request_review(request, slug):
    sent = publishing.request_review(_scenario(slug).pk, request.user)
    if sent:
        messages.success(request, f"Review requested: {sent} publisher{'s' if sent != 1 else ''} notified.")
    else:
        messages.info(request, "A review was requested a few minutes ago; the publishers already have it.")
    return redirect("studio:check", slug=slug)


@studio_required()
def versions(request, slug):
    from .views import _wizard
    scenario = _scenario(slug)
    rows = list(scenario.versions.select_related("published_by"))        # newest first
    for row, older in zip(rows, rows[1:] + [None]):
        # Studio publishes store their summary; seed snapshots are compared with the one before.
        row.changes = (row.meta or {}).get("changes") or publishing.what_changed(
            older.content if older else None, older.meta if older else None, row.content, row.meta or {})
    return render(request, "practice/studio/versions.html", _wizard(
        request, scenario, 4, "Version history", versions=rows, can_publish=request.user.has_perm(PUBLISH),
    ))
