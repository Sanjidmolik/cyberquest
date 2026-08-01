"""
games/urls.py
----------------
Routes belonging ONLY to the games app.
"""

from django.urls import path
from . import views

app_name = "games"

urlpatterns = [
    path("phishing-simulator/", views.phishing_simulator, name="phishing_simulator"),
    path("password-cracker/", views.password_cracker, name="password_cracker"),
]
