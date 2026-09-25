from django.urls import path
from . import views

app_name = "practice"

urlpatterns = [
    path("", views.practice_center, name="center"),
    path("cyber-dna/", views.cyber_dna_view, name="cyber_dna"),
    path("history/", views.practice_history, name="history"),
    path("session/<int:session_id>/", views.play_session, name="play"),
    path("session/<int:session_id>/open/", views.open_console, name="open"),
    path("session/<int:session_id>/decide/", views.submit_decision, name="decide"),
    path("session/<int:session_id>/result/", views.practice_result, name="result"),
    path("<slug:domain>/start/", views.start_practice, name="start"),
    path("<slug:domain>/", views.domain_detail, name="domain"),
]
