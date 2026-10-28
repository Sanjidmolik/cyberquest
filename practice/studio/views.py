"""Practice Studio pages in the Admin Command Center: the session list and the start screen
(duplicate, template, import). Every view checks permissions on the server (studio_required)."""

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..models import Scenario
from .access import studio_required
from .forms import ImportForm, ListFilterForm, TemplateStartForm
from .serializers import STEP_NAMES
from .services import SessionFileError, duplicate, from_template, import_session
from .starter_templates import KINDS, all_templates

ADD = "practice.add_scenario"


def _shell(request, title, **extra):
    """Context for dashboard/ops/base.html; superuser-only counts stay out for editors."""
    extra.update({"active": "studio", "page_title": title})
    if request.user.is_superuser:
        from pages.models import ContactMessage
        extra["open_contact"] = ContactMessage.objects.filter(is_resolved=False).count()
    return extra


def _step_names(content):
    return [STEP_NAMES.get(step.get("type"), step.get("type")) for step in (content or {}).get("steps") or []]


def _created(request, scenario, how):
    messages.success(request, f"Draft “{scenario.title}” {how}. Students won’t see it until it is published.")
    return redirect(f"{reverse('studio:list')}?created={scenario.slug}")


@studio_required()
def session_list(request):
    form = ListFilterForm(request.GET or None)
    rows = Scenario.objects.select_related("topic", "updated_by").order_by("-updated_at", "slug")
    if form.is_valid():
        data = form.cleaned_data
        if data["q"]:
            rows = rows.filter(Q(title__icontains=data["q"]) | Q(slug__icontains=data["q"]))
        if data["topic"]:
            rows = rows.filter(topic=data["topic"])
        if data["kind"]:
            rows = rows.filter(kind=data["kind"])
        if data["status"]:
            rows = rows.filter(status=data["status"])
    counts = {key: Scenario.objects.filter(status=key).count() for key, _ in Scenario.STATUS}
    return render(request, "practice/studio/list.html", _shell(
        request, "All sessions", form=form, rows=rows, counts=counts, total=sum(counts.values()),
        created=request.GET.get("created", ""), filtered=bool(request.GET.get("q") or request.GET.get("topic")
                                                              or request.GET.get("kind") or request.GET.get("status")),
    ))


@studio_required(ADD)
def start(request):
    templates = all_templates()
    cards = [{"kind": kind, "title": templates[kind]["title"],
              "steps": _step_names(templates[kind]["content"])} for kind in KINDS]
    return render(request, "practice/studio/start.html", _shell(
        request, "New practice session", templates=cards, template_form=TemplateStartForm(),
        published=Scenario.objects.filter(status=Scenario.PUBLISHED).count(),
    ))


@studio_required(ADD)
def duplicate_picker(request):
    if request.method == "POST":
        source = get_object_or_404(Scenario, slug=request.POST.get("source", ""))
        return _created(request, duplicate(source, request.user), f"copied from “{source.title}”")
    form = ListFilterForm(request.GET or None)
    rows = Scenario.objects.select_related("topic").exclude(status=Scenario.ARCHIVED).order_by("topic__order", "slug")
    if form.is_valid():
        data = form.cleaned_data
        if data["q"]:
            rows = rows.filter(Q(title__icontains=data["q"]) | Q(slug__icontains=data["q"]))
        if data["topic"]:
            rows = rows.filter(topic=data["topic"])
        if data["kind"]:
            rows = rows.filter(kind=data["kind"])
    rows = list(rows)
    for row in rows:
        row.step_names = _step_names(row.content)
    return render(request, "practice/studio/duplicate.html", _shell(
        request, "Duplicate a session", form=form, rows=rows))


@studio_required(ADD)
@require_POST
def template_create(request, kind):
    if kind not in KINDS:
        return redirect("studio:start")
    form = TemplateStartForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a topic for the new session.")
        return redirect("studio:start")
    scenario = from_template(kind, form.cleaned_data["topic"], request.user)
    return _created(request, scenario, f"created from the {kind} template")


@studio_required(ADD)
def import_file(request):
    form = ImportForm(request.POST or None, request.FILES or None)
    problems = []
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["file"]
        try:
            scenario = import_session(upload.read(), request.user, form.cleaned_data["topic"], upload.name)
        except SessionFileError as exc:
            problems = exc.messages
        else:
            return _created(request, scenario, f"imported from {upload.name}")
    return render(request, "practice/studio/import.html", _shell(
        request, "Import a session", form=form, problems=problems))
