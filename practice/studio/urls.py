from django.urls import path

from . import views

app_name = "studio"

urlpatterns = [
    path("", views.session_list, name="list"),
    path("new/", views.start, name="start"),
    path("new/duplicate/", views.duplicate_picker, name="duplicate"),
    path("new/template/<slug:kind>/", views.template_create, name="template"),
    path("new/import/", views.import_file, name="import"),
    path("<slug:slug>/basics/", views.wizard_basics, name="basics"),
    path("<slug:slug>/steps/", views.wizard_steps, name="steps"),
    path("<slug:slug>/save/", views.wizard_save, name="save"),
]
