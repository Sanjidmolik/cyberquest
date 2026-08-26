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
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(pattern_name='accounts:login', permanent=False)),
    path('accounts/', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('courses/', include('courses.urls')),
    path('games/', include('games.urls')),
    path('badges/', include('achievements.urls')),
    path('', include('pages.urls')),
    path('notifications/', include('notifications.urls')),
    path('leaderboard/', include('leaderboard.urls')),
    path('certificate/', include('certificates.urls')),
]

# Serve user-uploaded files (profile pictures) during development.
# In production this would be handled by the web server / a cloud storage
# service instead -- this line only applies while DEBUG=True.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
