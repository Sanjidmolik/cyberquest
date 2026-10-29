from django.urls import path

from . import panel_views as views

app_name = "blog_panel"

urlpatterns = [
    path("", views.post_list, name="list"),
    path("new/", views.post_new, name="new"),
    path("<int:pk>/", views.post_edit, name="edit"),
    path("<int:pk>/publish/", views.post_publish, name="publish"),
    path("<int:pk>/images/", views.image_upload, name="image_upload"),
    path("images/<str:public_id>/", views.image_action, name="image_action"),
]
