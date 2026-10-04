from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.signup_view, name="signup"),
    path("login/", views.login_view, name="login"),
    path("verify-login/", views.verify_login_pin, name="verify_login"),
    path("verify-totp/", views.verify_totp_login, name="verify_totp"),
    path("forgot-password/", views.forgot_password_view, name="forgot_password"),
    path("reset-password/", views.reset_password_view, name="reset_password"),
    path("logout/", views.logout_view, name="logout"),
    path("settings/", views.profile_settings, name="settings"),
    path("settings/2fa/start/", views.totp_start, name="totp_start"),
    path("settings/2fa/confirm/", views.totp_confirm, name="totp_confirm"),
    path("settings/2fa/disable/", views.totp_disable, name="totp_disable"),
    path("google/login/", views.google_login_start, name="google_login"),
    path("google/callback/", views.google_login_callback, name="google_callback"),
    path("complete-profile/", views.complete_profile_view, name="complete_profile"),
]