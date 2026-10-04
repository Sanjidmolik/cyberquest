from django.urls import path
from . import views

urlpatterns = [
    path("<slug:topic>/", views.learning_course, name="learning"),
]
