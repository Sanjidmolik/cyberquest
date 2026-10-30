"""Validate and re-encode uploaded blog images.

The checks and metadata stripping live in cyberquest/images.py (shared with message photos).
Here each picture is saved as two files with random names: max 1600 px wide, and a 640 px
thumbnail.
"""

import uuid

from django.core.files.base import ContentFile

from cyberquest.images import FORMATS, MAX_BYTES, MAX_PIXELS, clean_image, encode, resized  # noqa: F401

MAX_WIDTH = 1600
THUMB_WIDTH = 640


def process(upload):
    """Return (image ContentFile, thumbnail ContentFile, width, height) or raise ValidationError."""
    clean, fmt = clean_image(upload)
    ext, out_fmt = FORMATS[fmt]
    main = resized(clean, MAX_WIDTH)
    thumb = resized(clean, THUMB_WIDTH)
    name = uuid.uuid4().hex
    return (ContentFile(encode(main, out_fmt), name=f"{name}.{ext}"),
            ContentFile(encode(thumb, out_fmt), name=f"{name}-thumb.{ext}"),
            main.width, main.height)
