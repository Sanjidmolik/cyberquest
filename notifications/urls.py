from django.urls import path
from . import views

app_name = "notifications"
urlpatterns = [
    path("", views.notification_list, name="list"),
    path("<int:pk>/go/", views.notification_redirect, name="redirect"),
]
