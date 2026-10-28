from django.urls import path
from . import session_views, views

app_name = "practice"

urlpatterns = [
    path("", views.practice_center, name="center"),
    path("cyber-dna/", views.cyber_dna_view, name="cyber_dna"),
    path("history/", views.practice_history, name="history"),
    path("session/<int:session_id>/", views.play_session, name="play"),
    path("session/<int:session_id>/open/", views.open_console, name="open"),
    path("session/<int:session_id>/decide/", views.submit_decision, name="decide"),
    path("session/<int:session_id>/result/", views.practice_result, name="result"),
    path("api/attempts/", session_views.api_start, name="api_start"),
    path("api/attempts/<int:attempt_id>/answer/", session_views.api_answer, name="api_answer"),
    path("api/attempts/<int:attempt_id>/complete/", session_views.api_complete, name="api_complete"),
    path("<slug:domain>/start/", views.start_practice, name="start"),
    # /practice/<slug>/ serves a practice topic, or an interactive scenario when the slug is not
    # a topic (domain_detail hands over). The "session" name exists so scenario links can be reversed.
    path("<slug:domain>/", views.domain_detail, name="domain"),
    path("<slug:slug>/", session_views.session_page, name="session"),
]
