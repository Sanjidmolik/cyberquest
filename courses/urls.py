from django.urls import path
from . import views

app_name = "courses"
urlpatterns = [
    path("intro/", views.course_list, name="intro"),
    path("intro/<str:code>/", views.course_detail, name="detail"),
    path("intro/<str:code>/save-progress/", views.save_reading_progress, name="save_progress"),
    path("intro/<str:code>/complete/", views.mark_course_complete, name="mark_complete"),
]
