from django.apps import AppConfig


class DashboardConfig(AppConfig):
    name = 'dashboard'

    def ready(self):
        from django.contrib import admin
        admin.site.index_template = "admin/cyberquest_index.html"
