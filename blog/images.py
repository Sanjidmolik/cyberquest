"""Validate and re-encode uploaded blog images.

- At most 5 MB; JPEG, PNG or WebP as Pillow sees it (the file name doesn't matter);
  Pillow's `verify()` must pass and the picture must not be absurdly large.
- Turned upright from EXIF, then re-encoded from pixels only, so EXIF (GPS, camera),
  XMP, ICC text and comments are all dropped.
- Saved as two files with random names: max 1600 px wide, and a 640 px thumbnail.
"""

import uuid
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000              # refuse decompression bombs well before Pillow's own limit
MAX_WIDTH = 1600
THUMB_WIDTH = 640
FORMATS = {"JPEG": ("jpg", "JPEG"), "PNG": ("png", "PNG"), "WEBP": ("webp", "WEBP")}


def _encode(picture, fmt):
    out = BytesIO()
    if fmt == "JPEG":
        picture.convert("RGB").save(out, "JPEG", quality=85, optimize=True)
    elif fmt == "PNG":
        picture.save(out, "PNG", optimize=True)
    else:
        picture.save(out, "WEBP", quality=85)
    return out.getvalue()


def _resized(picture, width):
    if picture.width <= width:
        return picture.copy()
    height = max(1, round(picture.height * width / picture.width))
    return picture.resize((width, height), Image.LANCZOS)


def process(upload):
    """Return (image ContentFile, thumbnail ContentFile, width, height) or raise ValidationError."""
    if upload.size > MAX_BYTES:
        raise ValidationError("Images can be at most 5 MB.")
    data = upload.read()
    if len(data) > MAX_BYTES:
        raise ValidationError("Images can be at most 5 MB.")
    try:
        with Image.open(BytesIO(data)) as probe:
            fmt = probe.format
            if fmt not in FORMATS:
                raise ValidationError("Use a JPEG, PNG or WebP image.")
            if probe.width * probe.height > MAX_PIXELS:
                raise ValidationError("That image is too large (more than 40 megapixels).")
            probe.verify()
        with Image.open(BytesIO(data)) as source:
            source.load()
            picture = ImageOps.exif_transpose(source)
            if picture.mode not in ("RGB", "RGBA", "L", "LA"):
                picture = picture.convert("RGBA" if "A" in picture.getbands() else "RGB")
            # A fresh image from the pixels alone: no metadata can come along.
            clean = Image.new(picture.mode, picture.size)
            clean.putdata(picture.getdata())
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ValidationError("That file isn't a valid JPEG, PNG or WebP image.")
    ext, out_fmt = FORMATS[fmt]
    main = _resized(clean, MAX_WIDTH)
    thumb = _resized(clean, THUMB_WIDTH)
    name = uuid.uuid4().hex
    return (ContentFile(_encode(main, out_fmt), name=f"{name}.{ext}"),
            ContentFile(_encode(thumb, out_fmt), name=f"{name}-thumb.{ext}"),
            main.width, main.height)
