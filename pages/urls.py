from django.urls import path
from . import views

app_name = "pages"
urlpatterns = [
    path("", views.home_view, name="home"),
    path("about/", views.about_view, name="about"),
    path("contact/", views.contact_view, name="contact"),
    path("search/", views.search_view, name="search"),
    path("privacy/", views.privacy_view, name="privacy"),
    path("terms/", views.terms_view, name="terms"),
    path("legal/notices/", views.notices_view, name="notices"),
]
