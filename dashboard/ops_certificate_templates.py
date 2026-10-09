"""Certificate template management inside the command center."""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from certificates.forms import CertificateTemplateForm
from certificates.layout import fields_outside_page, placeholder_report
from certificates.models import CertificateTemplate
from certificates.services.generator import (
    editor_field_config,
    generate_certificate_pdf,
    page_metrics,
    pdf_bytes_to_png,
)
from certificates.services.qr import build_verification_url
from cyberquest.media_access import stored_file_path

from .ops_access import superuser_required
from .ops_views import _shell

SAMPLE_NAME = "Sample Learner"
SAMPLE_SCORE = 85
SAMPLE_ID = "SAMPLE-ONLY"


def _file_path(template):
    stored = stored_file_path(template.pdf_file)
    return str(stored) if stored else None


@superuser_required
@require_http_methods(["GET", "HEAD"])
def template_list(request):
    ctx = _shell(request, "certificate_templates", "Certificate templates")
    ctx["templates"] = CertificateTemplate.objects.all()
    return render(request, "dashboard/ops/certificate_templates.html", ctx)


@superuser_required
@require_http_methods(["GET", "POST", "HEAD"])
def template_create(request):
    form = CertificateTemplateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        template = form.save()
        for warning in form.layout_warnings:
            messages.warning(request, warning)
        messages.success(request, f"Saved {template.name}.")
        return redirect("ops:certificate_template_edit", pk=template.pk)
    ctx = _shell(request, "certificate_templates", "New certificate template")
    ctx.update({"form": form, "template": None, "editor": None})
    return render(request, "dashboard/ops/certificate_template_form.html", ctx)


@superuser_required
@require_http_methods(["GET", "POST", "HEAD"])
def template_edit(request, pk):
    template = get_object_or_404(CertificateTemplate, pk=pk)
    form = CertificateTemplateForm(
        request.POST or None,
        request.FILES or None,
        instance=template,
    )
    if request.method == "POST" and form.is_valid():
        template = form.save()
        for warning in form.layout_warnings:
            messages.warning(request, warning)
        messages.success(request, f"Saved {template.name}.")
        if request.POST.get("continue"):
            return redirect("ops:certificate_template_edit", pk=template.pk)
        return redirect("ops:certificate_templates")
    ctx = _shell(request, "certificate_templates", template.name)
    ctx.update({
        "form": form,
        "template": template,
        "editor": _editor_context(template),
    })
    return render(request, "dashboard/ops/certificate_template_form.html", ctx)


@superuser_required
@require_POST
def template_activate(request, pk):
    template = get_object_or_404(CertificateTemplate, pk=pk)
    path = _file_path(template)
    if path is None:
        messages.error(request, "This template file is missing.")
        return redirect("ops:certificate_template_edit", pk=pk)
    config = editor_field_config(path, template.template_kind, template.field_config or {})
    problems = []
    try:
        from certificates.layout import activation_errors
        problems = activation_errors(path, template.template_kind, config)
    except Exception as exc:
        problems = [str(exc)]
    if problems:
        for problem in problems:
            messages.error(request, problem)
        return redirect("ops:certificate_template_edit", pk=pk)
    template.is_active = True
    template.save(update_fields=["is_active", "updated_at"])
    messages.success(request, f"{template.name} is now the active template.")
    return redirect("ops:certificate_templates")


@superuser_required
@require_POST
def template_deactivate(request, pk):
    template = get_object_or_404(CertificateTemplate, pk=pk)
    template.is_active = False
    template.save(update_fields=["is_active", "updated_at"])
    messages.success(request, f"{template.name} is no longer the active template.")
    return redirect("ops:certificate_templates")


@superuser_required
@require_POST
def template_delete(request, pk):
    template = get_object_or_404(CertificateTemplate, pk=pk)
    name = template.name
    template.delete()
    messages.success(request, f"Deleted {name}. Issued certificate PDFs were left unchanged.")
    return redirect("ops:certificate_templates")


@superuser_required
@require_http_methods(["GET", "HEAD"])
def template_artwork(request, pk):
    template = get_object_or_404(CertificateTemplate, pk=pk)
    path = _file_path(template)
    if path is None:
        return HttpResponse(status=404)
    if template.template_kind == "image":
        with open(path, "rb") as handle:
            payload = handle.read()
        content_type = "image/png" if path.lower().endswith(".png") else "image/jpeg"
        return HttpResponse(payload, content_type=content_type)
    with open(path, "rb") as handle:
        png = pdf_bytes_to_png(handle.read(), zoom=2)
    return HttpResponse(png, content_type="image/png")


@superuser_required
@require_http_methods(["GET", "HEAD"])
def template_sample_preview(request, pk):
    """Render sample data through the issuance pipeline. Nothing is saved."""
    template = get_object_or_404(CertificateTemplate, pk=pk)
    before = template.issued_certificates.count()
    issued_at = timezone.localtime()
    pdf = generate_certificate_pdf(
        recipient_name=SAMPLE_NAME,
        score=SAMPLE_SCORE,
        certificate_id=SAMPLE_ID,
        issued_date_display=issued_at.strftime("%d %B %Y"),
        verify_url=build_verification_url(SAMPLE_ID, request),
        template=template,
        require_template=True,
    )
    template.refresh_from_db()
    if template.issued_certificates.count() != before:
        raise RuntimeError("Sample preview must not create an issued certificate.")
    return HttpResponse(pdf_bytes_to_png(pdf), content_type="image/png")


def _editor_context(template):
    path = _file_path(template)
    if path is None:
        return None
    try:
        report = placeholder_report(path, template.template_kind)
        width, height = page_metrics(path, template.template_kind)
    except Exception:
        return None
    config = editor_field_config(path, template.template_kind, template.field_config or {})
    return {
        "config": config,
        "page_width": width,
        "page_height": height,
        "placeholders": sorted(report["placeholders"]),
        "unknown": report["unknown"],
        "outside": fields_outside_page(config, width, height),
        "artwork_url": f"/admin-dashboard/certificates/templates/{template.pk}/artwork.png",
        "preview_url": f"/admin-dashboard/certificates/templates/{template.pk}/preview.png",
    }
