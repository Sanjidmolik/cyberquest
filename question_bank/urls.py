from django.urls import path

from . import views

app_name = "question_bank"

urlpatterns = [
    path("question-banks/", views.question_bank_list_create, name="bank_list_create"),
    path("question-banks/<int:bank_id>/", views.question_bank_detail, name="bank_detail"),
    path("question-banks/<int:bank_id>/generate/", views.question_bank_generate, name="bank_generate"),
    path("question-banks/<int:bank_id>/sets/", views.question_bank_sets, name="bank_sets"),
    path("question-sets/<int:set_id>/questions/", views.question_set_questions, name="set_questions"),
    path("question-sets/<int:set_id>/approve/", views.question_set_approve, name="set_approve"),
    path("question-sets/<int:set_id>/reject/", views.question_set_reject, name="set_reject"),
]
