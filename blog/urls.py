from django.urls import path

from . import views

app_name = "blog"

urlpatterns = [
    path("", views.post_list, name="list"),
    path("preview/<str:token>/", views.preview, name="preview"),
    path("img/<str:public_id>/", views.image, name="image"),
    path("img/<str:public_id>/thumb/", views.image, {"variant": "thumb"}, name="thumb"),
    path("<slug:slug>/", views.post_detail, name="detail"),
]
