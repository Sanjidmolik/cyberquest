"""
Open stored uploads only when their path stays inside MEDIA_ROOT.

Callers pass a model FileField. Client-supplied paths are never accepted.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.http import FileResponse


def stored_file_path(field) -> Path | None:
    """Return the resolved file path, or None when it is missing or unsafe."""
    name = str(getattr(field, "name", "") or "").strip()
    if not name:
        return None
    portable = PurePosixPath(name.replace("\\", "/"))
    if portable.is_absolute() or portable.anchor or ".." in portable.parts:
        return None
    root = Path(settings.MEDIA_ROOT).resolve()
    try:
        path = (root / name).resolve()
        path.relative_to(root)
    except (OSError, ValueError):
        return None
    if not path.is_file():
        return None
    return path


def serve_stored_file(field, *, as_attachment: bool = False, filename: str = "", content_type: str = ""):
    """Stream a validated stored file, or return None when it cannot be opened."""
    path = stored_file_path(field)
    if path is None:
        return None
    guessed = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if path.suffix.lower() == ".pdf":
        guessed = "application/pdf"
    download_name = filename or path.name
    return FileResponse(
        path.open("rb"),
        as_attachment=as_attachment,
        filename=download_name,
        content_type=guessed,
    )
