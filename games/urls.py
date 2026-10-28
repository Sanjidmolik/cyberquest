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
    # Defence-curriculum missions, one per course.
    path("online-safety/", views.quiz_game, {"game_key": "online_safety"}, name="online_safety"),
    path("malware-defence/", views.quiz_game, {"game_key": "malware_defense"}, name="malware_defense"),
    path("device-protection/", views.quiz_game, {"game_key": "device_protection"}, name="device_protection"),
    path("privacy-shield/", views.quiz_game, {"game_key": "privacy_defense"}, name="privacy_defense"),
    path("incident-response/", views.quiz_game, {"game_key": "incident_response"}, name="incident_response"),
]
