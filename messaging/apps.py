from django.apps import AppConfig


class MessagingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "messaging"
    verbose_name = "Messaging"

    def ready(self):
        from . import checks, signals  # noqa: F401  (register the key check and deletion handling)
