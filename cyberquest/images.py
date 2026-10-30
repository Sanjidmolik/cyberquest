"""Checking and cleaning uploaded images (shared by the blog and view-once message photos).

- At most 5 MB; JPEG, PNG or WebP as Pillow sees it (the file name doesn't matter);
  Pillow's `verify()` must pass and the picture must not be absurdly large.
- Turned upright from EXIF, then rebuilt from pixels only, so EXIF (GPS, camera), XMP,
  ICC text and comments are all dropped.
"""

from io import BytesIO

from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000              # refuse decompression bombs well before Pillow's own limit
FORMATS = {"JPEG": ("jpg", "JPEG"), "PNG": ("png", "PNG"), "WEBP": ("webp", "WEBP")}


def encode(picture, fmt):
    out = BytesIO()
    if fmt == "JPEG":
        picture.convert("RGB").save(out, "JPEG", quality=85, optimize=True)
    elif fmt == "PNG":
        picture.save(out, "PNG", optimize=True)
    else:
        picture.save(out, "WEBP", quality=85)
    return out.getvalue()


def resized(picture, width):
    if picture.width <= width:
        return picture.copy()
    height = max(1, round(picture.height * width / picture.width))
    return picture.resize((width, height), Image.LANCZOS)


def clean_image(upload):
    """Return (clean PIL image without metadata, Pillow format name) or raise ValidationError."""
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
    return clean, fmt
