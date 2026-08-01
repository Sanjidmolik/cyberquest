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

urlpatterns = [
    path('admin/', admin.site.urls),

    # Each feature app owns its own urls.py — this project file just
    # "plugs them in" under a prefix. Nothing about login/dashboard logic
    # lives in this file, on purpose.
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('courses/', include('courses.urls')),
    path('games/', include('games.urls')),

    # Visiting the bare root URL "/" just sends the visitor to the login page
    path('', RedirectView.as_view(pattern_name='accounts:login', permanent=False)),
]
