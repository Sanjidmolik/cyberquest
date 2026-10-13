"""Deployment checks for storage that would silently lose data on Render."""

import os

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.database, deploy=True)
def persistent_storage_check(app_configs, **kwargs):
    issues = []
    on_render = bool(os.environ.get("RENDER") or os.environ.get("RENDER_EXTERNAL_HOSTNAME"))
    engine = settings.DATABASES["default"]["ENGINE"]
    if on_render and engine.endswith("sqlite3"):
        issues.append(Warning(
            "The database is SQLite on Render, whose filesystem is wiped on every deploy.",
            hint="Set DATABASE_URL to the Render PostgreSQL connection string.",
            id="cyberquest.W001",
        ))
    uses_r2 = getattr(settings, "MEDIA_STORAGE", "filesystem") == "r2"
    if on_render and not uses_r2 and not (os.environ.get("MEDIA_ROOT") or "").strip():
        issues.append(Warning(
            "Uploads and issued certificate PDFs are stored on the service's own disk, "
            "which Render Free wipes on every deploy, restart and spin-down.",
            hint="Set MEDIA_STORAGE=r2 with the R2_* variables (see DEPLOYMENT.md), "
                 "or point MEDIA_ROOT at a persistent disk on a paid plan.",
            id="cyberquest.W002",
        ))
    return issues
