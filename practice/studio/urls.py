from django.urls import path

from . import preview_views, publish_views, views

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
    path("<slug:slug>/preview/", preview_views.wizard_preview, name="preview"),
    path("<slug:slug>/preview/play/", preview_views.play, name="play"),
    path("<slug:slug>/check/", publish_views.wizard_check, name="check"),
    path("<slug:slug>/publish/", publish_views.publish, name="publish"),
    path("<slug:slug>/archive/", publish_views.archive, name="archive"),
    path("<slug:slug>/unarchive/", publish_views.unarchive, name="unarchive"),
    path("<slug:slug>/review/", publish_views.request_review, name="review"),
    path("<slug:slug>/versions/", publish_views.versions, name="versions"),
    path("<slug:slug>/versions/<int:version>/restore/", publish_views.restore, name="restore"),
]
