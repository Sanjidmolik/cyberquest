"""
courses/urls.py
------------------
Routes belonging ONLY to the courses app.
"""

from django.urls import path
from . import views

app_name = "courses"

urlpatterns = [
    # kept as name="intro" so accounts/routing.py, dashboard/views.py, and
    # games/views.py (which all redirect to "courses:intro") don't need to change
    path("intro/", views.course_list, name="intro"),
    path("intro/<str:code>/", views.course_detail, name="detail"),
]
