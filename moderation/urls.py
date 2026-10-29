from django.urls import path

from . import views

app_name = "moderation_public"

urlpatterns = [
    path("report/", views.report, name="report"),
    path("notices/", views.notices, name="notices"),
]
