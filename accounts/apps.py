from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        from . import checks  # noqa: F401  (registers deploy checks)
        from cyberquest import checks as _site_checks  # noqa: F401
