"""
Phase 1 — Steps 5 and 6: storage-independent access to private uploads.

Callers pass a model FileField. Client-supplied paths are never accepted.

Local development keeps Django's FileSystemStorage under MEDIA_ROOT, and the
containment check below stays exactly as before. In production the same
fields can live in a private Cloudflare R2 bucket (cyberquest.storage).
Either way, files are only ever streamed through the permission-checked views
that call serve_stored_file(); no page links to a bucket URL.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage, default_storage
from django.http import FileResponse

logger = logging.getLogger(__name__)


def safe_name(field) -> str | None:
    """The stored name, or None when it is empty or could escape the storage root."""
    name = str(getattr(field, "name", "") or "").strip()
    if not name:
        return None
    portable = PurePosixPath(name.replace("\\", "/"))
    if portable.is_absolute() or portable.anchor or ".." in portable.parts:
        return None
    return name


def _storage(field):
    return getattr(field, "storage", None) or default_storage


def is_local(field) -> bool:
    return isinstance(_storage(field), FileSystemStorage)


def stored_file_path(field) -> Path | None:
    """Resolved path for a file in local storage, or None (missing, unsafe, or remote)."""
    name = safe_name(field)
    if name is None or not is_local(field):
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


def _remote_exists(field, name: str) -> bool:
    try:
        return bool(_storage(field).exists(name))
    except Exception:
        # Network or credential problems are logged without object details.
        logger.warning("Remote storage existence check failed", exc_info=False)
        return False


def file_exists(field, *, cache_seconds: int = 0) -> bool:
    """True when the stored file can be opened.

    Remote checks cost a request, so callers that run on every page view
    (course cards) pass cache_seconds. Stored names are never reused
    (file_overwrite is off), so caching by name cannot serve stale content.
    """
    name = safe_name(field)
    if name is None:
        return False
    if is_local(field):
        return stored_file_path(field) is not None
    if not cache_seconds:
        return _remote_exists(field, name)
    key = f"media_exists:{name}"
    cached = cache.get(key)
    if cached is None:
        cached = _remote_exists(field, name)
        cache.set(key, cached, cache_seconds)
    return bool(cached)


def open_stored_file(field):
    """An open binary file object for a stored file, or None when it cannot be opened."""
    name = safe_name(field)
    if name is None:
        return None
    if is_local(field):
        path = stored_file_path(field)
        return path.open("rb") if path is not None else None
    try:
        return _storage(field).open(name, "rb")
    except Exception:
        logger.warning("Stored file could not be opened from remote storage", exc_info=False)
        return None


def read_stored_bytes(field) -> bytes | None:
    handle = open_stored_file(field)
    if handle is None:
        return None
    try:
        return handle.read()
    finally:
        handle.close()


def serve_stored_file(field, *, as_attachment: bool = False, filename: str = "", content_type: str = ""):
    """Stream a validated stored file, or return None when it cannot be opened."""
    name = safe_name(field)
    handle = open_stored_file(field)
    if name is None or handle is None:
        return None
    base = PurePosixPath(name.replace("\\", "/")).name
    guessed = content_type or mimetypes.guess_type(base)[0] or "application/octet-stream"
    if base.lower().endswith(".pdf"):
        guessed = "application/pdf"
    response = FileResponse(
        handle,
        as_attachment=as_attachment,
        filename=filename or base,
        content_type=guessed,
    )
    # Private files: browsers may keep them, shared caches and proxies may not.
    response["Cache-Control"] = "private, max-age=300"
    return response


@contextmanager
def local_copy(field):
    """Yield a filesystem path for libraries that need one (PyMuPDF, Pillow), or None.

    Local storage yields the real file. Remote storage downloads the object to
    a private temporary file that is deleted when the block ends.
    """
    path, temporary = materialize(field)
    try:
        yield path
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def materialize(field):
    """Like local_copy(), for callers that manage cleanup themselves.

    Returns (path, temporary). `temporary` is the same path when a download
    was made and must be deleted by the caller; it is None for local files.
    """
    name = safe_name(field)
    if name is None:
        return None, None
    if is_local(field):
        return stored_file_path(field), None
    data = read_stored_bytes(field)
    if data is None:
        return None, None
    fd, temp_name = tempfile.mkstemp(suffix=PurePosixPath(name).suffix.lower())
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    return Path(temp_name), Path(temp_name)
