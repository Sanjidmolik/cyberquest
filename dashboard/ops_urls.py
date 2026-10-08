from django.urls import path

from . import ops_views

app_name = "ops"

urlpatterns = [
    path("", ops_views.overview, name="overview"),
    path("students/", ops_views.students, name="students"),
    path("students/<int:pk>/", ops_views.student_detail, name="student"),
    path("courses/", ops_views.courses, name="courses"),
    path("games/", ops_views.games, name="games"),
    path("practice/", ops_views.practice, name="practice"),
    path("questions/", ops_views.questions, name="questions"),
    path("review/", ops_views.review, name="review"),
    path("review/<int:pk>/approve/", ops_views.approve_bank, name="approve_bank"),
    path("review/set/<int:pk>/reject/", ops_views.reject_set, name="reject_set"),
    path("certificates/", ops_views.certificates, name="certificates"),
    path("achievements/", ops_views.achievements, name="achievements"),
    path("leaderboard/", ops_views.leaderboard, name="leaderboard"),
    path("notifications/", ops_views.notifications, name="notifications"),
    path("contact/", ops_views.contact, name="contact"),
    path("contact/<int:pk>/resolve/", ops_views.resolve_contact, name="resolve_contact"),
    path("search/", ops_views.search, name="search"),
    path("analytics/", ops_views.analytics, name="analytics"),
    path("settings/", ops_views.settings_page, name="settings"),
]
