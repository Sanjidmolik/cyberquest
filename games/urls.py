from django.urls import path
from . import views

app_name = "games"
urlpatterns = [
    # One generic route serves every quiz-style game defined in quiz_data.py.
    path("phishing-simulator/", views.quiz_game, {"game_key": "phishing_simulator"}, name="phishing_simulator"),
    path("password-cracker/", views.quiz_game, {"game_key": "password_cracker"}, name="password_cracker"),
    path("cryptography/", views.quiz_game, {"game_key": "cryptography"}, name="cryptography"),
    path("osint/", views.quiz_game, {"game_key": "osint"}, name="osint"),
    path("steganography/", views.quiz_game, {"game_key": "steganography"}, name="steganography"),
    path("network-defense/", views.quiz_game, {"game_key": "network_defense"}, name="network_defense"),
]
