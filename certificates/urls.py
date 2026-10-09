from django.urls import path

from . import views

app_name = "certificates"
urlpatterns = [
    path("", views.certificate_page, name="page"),
    path("preview.png", views.certificate_preview, name="preview"),
    path("generate/", views.certificate_generate, name="generate"),
    path("view/", views.certificate_view_pdf, name="view"),
    path("download/", views.certificate_download, name="download"),
    path("template/<int:pk>/file/", views.template_file, name="template_file"),
    path("signature/<int:pk>/file/", views.signature_file, name="signature_file"),
    path("issued/<int:pk>/file/", views.issued_file, name="issued_file"),
    path("verify/<str:certificate_id>/", views.verify_certificate, name="verify"),
]
