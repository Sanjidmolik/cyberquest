from django.urls import path

from . import panel_views as views

app_name = "moderation"

urlpatterns = [
    path("", views.queue, name="queue"),
    path("reports/<int:pk>/", views.report_detail, name="report"),
    path("reports/<int:pk>/show/", views.reveal, name="reveal"),
    path("reports/<int:pk>/act/", views.act, name="act"),
    path("restrictions/", views.restrictions, name="restrictions"),
    path("restrictions/<int:pk>/lift/", views.lift, name="lift"),
    path("log/", views.log, name="log"),
]
