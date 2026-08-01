"""
dashboard/urls.py
--------------------
Routes belonging ONLY to the dashboard app. Self-contained, same pattern
as accounts/urls.py, so this app can be swapped/rebuilt independently.
"""

from django.urls import path
from . import views

app_name = "dashboard"  # lets us reference this as "dashboard:home"

urlpatterns = [
    path("", views.dashboard_home, name="home"),
]
