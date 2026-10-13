"""
Phase 1 — Steps 3 and 4: build the default-storage setting from the environment.

Kept free of boto3 imports so local development (filesystem storage) never
loads the S3 client. Error messages name missing variables, never values.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

FILESYSTEM = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
R2_BACKEND = "cyberquest.storage.PrivateR2Storage"


def _bounded_int(raw: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int((raw or "").strip())
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default


def media_storage_mode(environ) -> str:
    mode = (environ.get("MEDIA_STORAGE") or "filesystem").strip().lower()
    if mode not in ("filesystem", "r2"):
        raise ImproperlyConfigured("MEDIA_STORAGE must be 'filesystem' or 'r2'.")
    return mode


def default_storage_setting(environ) -> dict:
    """STORAGES["default"] for the given environment mapping."""
    if media_storage_mode(environ) != "r2":
        return dict(FILESYSTEM)

    def value(name):
        return (environ.get(name) or "").strip()

    required = {name: value(name) for name in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")}
    endpoint = value("R2_ENDPOINT_URL").rstrip("/")
    if not endpoint and value("R2_ACCOUNT_ID"):
        endpoint = f"https://{value('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"
    missing = [name for name, found in required.items() if not found]
    if not endpoint:
        missing.append("R2_ENDPOINT_URL or R2_ACCOUNT_ID")
    if missing:
        raise ImproperlyConfigured(
            "MEDIA_STORAGE=r2 needs these environment variables: " + ", ".join(missing)
        )
    if not endpoint.startswith("https://"):
        raise ImproperlyConfigured("R2_ENDPOINT_URL must start with https://.")
    return {
        "BACKEND": R2_BACKEND,
        "OPTIONS": {
            "bucket_name": required["R2_BUCKET_NAME"],
            "endpoint_url": endpoint,
            "access_key": required["R2_ACCESS_KEY_ID"],
            "secret_key": required["R2_SECRET_ACCESS_KEY"],
            "region_name": value("R2_REGION") or "auto",
            # Object keys become "<prefix>/<upload_to>/<file>", e.g. media/profile_pictures/a.png.
            "location": (value("R2_MEDIA_PREFIX") or "media").strip("/"),
            "querystring_expire": _bounded_int(value("R2_SIGNED_URL_SECONDS"), 300, 60, 3600),
        },
    }
