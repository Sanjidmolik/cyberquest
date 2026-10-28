from django.urls import path

from . import views

app_name = "studio"

urlpatterns = [
    path("", views.session_list, name="list"),
    path("new/", views.start, name="start"),
    path("new/duplicate/", views.duplicate_picker, name="duplicate"),
    path("new/template/<slug:kind>/", views.template_create, name="template"),
    path("new/import/", views.import_file, name="import"),
]
