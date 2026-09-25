from django.urls import path
from . import views

app_name = "certificates"
urlpatterns = [
    path("", views.certificate_page, name="page"),
    path("download/", views.certificate_download, name="download"),
    path("verify/<str:certificate_id>/", views.verify_certificate, name="verify"),
]