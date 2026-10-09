"""
URL configuration for cyberquest project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.templatetags.static import static as static_url

from accounts.views import admin_login_view
from certificates.views import verify_certificate

urlpatterns = [
    path('admin-login/', admin_login_view, name='admin_login'),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('admin-dashboard/', include('dashboard.ops_urls')),
    path('courses/', include('courses.urls')),
    path('learning/', include('courses.learning_urls')),
    path('games/', include('games.urls')),
    path('badges/', include('achievements.urls')),
    path('', include('pages.urls')),
    path('notifications/', include('notifications.urls')),
    path('leaderboard/', include('leaderboard.urls')),
    path('certificate/', include('certificates.urls')),
    # Public QR verification URL (canonical for certificate QR codes)
    path('verify/<str:certificate_id>/', verify_certificate, name='certificate_verify'),
    path('practice/', include('practice.urls')),
    path('api/', include('question_bank.urls')),
    path('favicon.ico', RedirectView.as_view(url=static_url('dashboard/img/favicon.ico'), permanent=True)),
]
