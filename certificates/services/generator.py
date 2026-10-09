"""
certificates/services/generator.py
----------------------------------
PyMuPDF-based certificate PDF generation.

Priority:
  1. Active admin-uploaded template (PDF, JPG, or PNG) — preserve design; fill fields
  2. Built-in CyberQuest default landscape certificate

Issued output is always a PDF (download / verify), even when the template is an image.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pymupdf
from django.conf import settings
from PIL import Image

from .qr import make_qr_png_bytes

logger = logging.getLogger(__name__)

# CyberQuest palette (matches shared theme / home page)
PURPLE = (102 / 255, 20 / 255, 216 / 255)
PURPLE_RICH = (112 / 255, 31 / 255, 211 / 255)
PURPLE_DEEP = (82 / 255, 14 / 255, 163 / 255)
LAVENDER = (181 / 255, 125 / 255, 236 / 255)
INK = (27 / 255, 16 / 255, 48 / 255)
INK_SOFT = (86 / 255, 74 / 255, 110 / 255)
PAPER = (1, 1, 1)
PAPER_TINT = (250 / 255, 247 / 255, 255 / 255)

PLACEHOLDERS = {
    "name": "{{NAME}}",
    "score": "{{SCORE}}",
    "date": "{{DATE}}",
    "certificate_id": "{{CERTIFICATE_ID}}",
    "qr": "{{QR}}",
}

DEFAULT_FIELD_CONFIG = {
    "name": {"x": 80, "y": 230, "w": 682, "h": 56, "fontsize": 36},
    "score": {"x": 80, "y": 320, "w": 682, "h": 36, "fontsize": 22},
    "date": {"x": 80, "y": 480, "w": 320, "h": 28, "fontsize": 12},
    "certificate_id": {"x": 80, "y": 508, "w": 320, "h": 28, "fontsize": 11},
    "qr": {"x": 700, "y": 460, "size": 90},
}

DEFAULT_SIGNATORIES = [
    {"name": "Muhammad Mahfuz Hasan", "title": "Course Director"},
    {"name": "Sanjidur Rahman Sanjid", "title": "Head of CyberQuest"},
]


def _font_paths() -> dict[str, Path]:
    base = Path(settings.BASE_DIR) / "certificates" / "static" / "certificates" / "fonts"
    return {
        "regular": base / "ComicNeue-Regular.ttf",
        "bold": base / "ComicNeue-Bold.ttf",
        "display": base / "Cinzel-Bold.ttf",
        "display_regular": base / "Cinzel-Regular.ttf",
    }


def _insert_font(page, path: Path, name: str) -> str | None:
    if path.is_file():
        try:
            page.insert_font(fontname=name, fontfile=str(path))
            return name
        except Exception:
            logger.exception("Could not embed font %s", path)
    return None


def _pick_fonts(page) -> dict[str, str]:
    paths = _font_paths()
    bold = _insert_font(page, paths["bold"], "cqbold") or "helv"
    regular = _insert_font(page, paths["regular"], "cqreg") or "helv"
    display = (
        _insert_font(page, paths["display"], "cqdisp")
        or _insert_font(page, paths["display_regular"], "cqdisp")
        or bold
    )
    return {"bold": bold, "regular": regular, "display": display}


def _fit_textbox(page, rect, text, fontname, max_size, min_size=10, color=INK, align=1):
    """Shrink font until the text fits the rect; return the size used."""
    size = float(max_size)
    while size >= min_size:
        overflow = page.insert_textbox(
            rect,
            text,
            fontsize=size,
            fontname=fontname,
            color=color,
            align=align,
            overlay=True,
        )
        if overflow >= 0:
            return size
        size -= 1.0
    page.insert_textbox(
        rect,
        text,
        fontsize=min_size,
        fontname=fontname,
        color=color,
        align=align,
        overlay=True,
    )
    return min_size


def _draw_centered(page, y, text, fontname, fontsize, color, page_width, margin=60):
    rect = pymupdf.Rect(margin, y, page_width - margin, y + fontsize * 1.6)
    _fit_textbox(page, rect, text, fontname, fontsize, min_size=8, color=color, align=1)


def _default_signatories():
    try:
        from certificates.models import Signatory

        rows = list(
            Signatory.objects.filter(is_active=True).order_by("order").values("name", "title")[:4]
        )
        if rows:
            return rows
    except Exception:
        pass
    return list(DEFAULT_SIGNATORIES)


def _build_default_pdf(payload: dict, qr_png: bytes) -> bytes:
    # Landscape A4 in points
    width, height = 842, 595
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    fonts = _pick_fonts(page)

    # Paper background
    page.draw_rect(pymupdf.Rect(0, 0, width, height), color=None, fill=PAPER)
    # Soft tint overlay
    page.draw_rect(pymupdf.Rect(0, 0, width, height), color=None, fill=PAPER_TINT, fill_opacity=0.35)

    # Outer purple frame
    outer = pymupdf.Rect(28, 28, width - 28, height - 28)
    page.draw_rect(outer, color=PURPLE_RICH, width=2.2)
    inner = pymupdf.Rect(40, 40, width - 40, height - 40)
    page.draw_rect(inner, color=LAVENDER, width=1.0)

    # Corner ornaments
    c = 18
    for x0, y0, dx, dy in (
        (48, 48, 1, 1),
        (width - 48, 48, -1, 1),
        (48, height - 48, 1, -1),
        (width - 48, height - 48, -1, -1),
    ):
        page.draw_line(pymupdf.Point(x0, y0), pymupdf.Point(x0 + dx * c, y0), color=PURPLE, width=2.4)
        page.draw_line(pymupdf.Point(x0, y0), pymupdf.Point(x0, y0 + dy * c), color=PURPLE, width=2.4)

    _draw_centered(page, 62, "CYBERQUEST", fonts["display"], 28, PURPLE, width)
    _draw_centered(page, 100, "CERTIFICATE OF ACHIEVEMENT", fonts["display"], 34, INK, width)
    # Accent rule
    page.draw_line(
        pymupdf.Point(width * 0.28, 148),
        pymupdf.Point(width * 0.72, 148),
        color=LAVENDER,
        width=1.2,
    )
    _draw_centered(
        page, 168, "This certificate is proudly presented to", fonts["regular"], 14, INK_SOFT, width
    )

    name_rect = pymupdf.Rect(90, 200, width - 90, 265)
    _fit_textbox(
        page,
        name_rect,
        payload["recipient_name"],
        fonts["display"],
        max_size=40,
        min_size=16,
        color=PURPLE_DEEP,
        align=1,
    )
    # Name underline
    page.draw_line(
        pymupdf.Point(width * 0.22, 272),
        pymupdf.Point(width * 0.78, 272),
        color=PURPLE,
        width=1.0,
    )

    _draw_centered(
        page,
        290,
        "for successfully completing CyberQuest.",
        fonts["regular"],
        14,
        INK_SOFT,
        width,
    )
    _draw_centered(
        page,
        322,
        f"Score: {payload['score']}%",
        fonts["bold"],
        20,
        PURPLE_RICH,
        width,
    )
    _draw_centered(page, 352, str(payload["score"]), fonts["display"], 42, PURPLE, width)
    _draw_centered(
        page, 404, "OVERALL COMPETENCY SCORE", fonts["bold"], 11, INK_SOFT, width
    )

    # Signatories
    sigs = _default_signatories()[:2]
    if len(sigs) == 1:
        positions = [width / 2]
    else:
        positions = [width * 0.28, width * 0.72]
    for sig, cx in zip(sigs, positions):
        name = sig["name"]
        title = sig["title"]
        page.insert_text(
            pymupdf.Point(cx - 90, 460),
            name,
            fontsize=12,
            fontname=fonts["bold"],
            color=INK,
        )
        page.draw_line(
            pymupdf.Point(cx - 95, 468),
            pymupdf.Point(cx + 95, 468),
            color=INK,
            width=0.8,
        )
        page.insert_text(
            pymupdf.Point(cx - 70, 484),
            title,
            fontsize=10,
            fontname=fonts["regular"],
            color=PURPLE_RICH,
        )

    # Meta + QR
    meta_x = 70
    page.insert_text(
        pymupdf.Point(meta_x, 530),
        f"Certificate ID: {payload['certificate_id']}",
        fontsize=10,
        fontname=fonts["regular"],
        color=INK,
    )
    page.insert_text(
        pymupdf.Point(meta_x, 548),
        f"Date Issued: {payload['issued_date_display']}",
        fontsize=10,
        fontname=fonts["regular"],
        color=INK,
    )

    qr_rect = pymupdf.Rect(width - 150, height - 150, width - 55, height - 55)
    page.insert_image(qr_rect, stream=qr_png)

    pdf_bytes = doc.tobytes(deflate=True, garbage=3)
    doc.close()
    return pdf_bytes


def _replace_placeholder_text(page, needle: str, replacement: str, fonts, fontsize=16, color=INK):
    hits = page.search_for(needle)
    for rect in hits:
        page.add_redact_annot(rect, fill=PAPER)
        page.apply_redactions(images=0)
        # Expand slightly for long replacements (esp. names)
        grow = max(0, len(replacement) - len(needle)) * (fontsize * 0.28)
        box = pymupdf.Rect(rect.x0 - grow / 2, rect.y0 - 2, rect.x1 + grow / 2 + 40, rect.y1 + 4)
        # Keep within page
        box = box & page.rect
        _fit_textbox(page, box, replacement, fonts["bold"], fontsize, min_size=8, color=color, align=1)
    return bool(hits)


def _place_qr_at_placeholder(page, qr_png: bytes):
    hits = page.search_for(PLACEHOLDERS["qr"])
    for rect in hits:
        page.add_redact_annot(rect, fill=PAPER)
        page.apply_redactions(images=0)
        size = max(rect.width, rect.height, 70)
        qr_rect = pymupdf.Rect(rect.x0, rect.y0, rect.x0 + size, rect.y0 + size)
        page.insert_image(qr_rect, stream=qr_png)
    return bool(hits)


def _overlay_from_config(page, config: dict, payload: dict, qr_png: bytes, fonts):
    cfg = {**DEFAULT_FIELD_CONFIG, **(config or {})}

    name_c = cfg.get("name", DEFAULT_FIELD_CONFIG["name"])
    name_rect = pymupdf.Rect(
        name_c["x"], name_c["y"], name_c["x"] + name_c["w"], name_c["y"] + name_c["h"]
    )
    _fit_textbox(
        page,
        name_rect,
        payload["recipient_name"],
        fonts["display"],
        max_size=float(name_c.get("fontsize", 36)),
        min_size=12,
        color=PURPLE_DEEP,
        align=1,
    )

    score_c = cfg.get("score", DEFAULT_FIELD_CONFIG["score"])
    score_rect = pymupdf.Rect(
        score_c["x"], score_c["y"], score_c["x"] + score_c["w"], score_c["y"] + score_c["h"]
    )
    _fit_textbox(
        page,
        score_rect,
        f"{payload['score']}%",
        fonts["bold"],
        max_size=float(score_c.get("fontsize", 22)),
        min_size=10,
        color=PURPLE_RICH,
        align=1,
    )

    date_c = cfg.get("date", DEFAULT_FIELD_CONFIG["date"])
    date_rect = pymupdf.Rect(
        date_c["x"], date_c["y"], date_c["x"] + date_c["w"], date_c["y"] + date_c["h"]
    )
    _fit_textbox(
        page,
        date_rect,
        payload["issued_date_display"],
        fonts["regular"],
        max_size=float(date_c.get("fontsize", 12)),
        min_size=8,
        color=INK,
        align=0,
    )

    id_c = cfg.get("certificate_id", DEFAULT_FIELD_CONFIG["certificate_id"])
    id_rect = pymupdf.Rect(id_c["x"], id_c["y"], id_c["x"] + id_c["w"], id_c["y"] + id_c["h"])
    _fit_textbox(
        page,
        id_rect,
        payload["certificate_id"],
        fonts["regular"],
        max_size=float(id_c.get("fontsize", 11)),
        min_size=8,
        color=INK,
        align=0,
    )

    qr_c = cfg.get("qr", DEFAULT_FIELD_CONFIG["qr"])
    size = float(qr_c.get("size", 90))
    qr_rect = pymupdf.Rect(qr_c["x"], qr_c["y"], qr_c["x"] + size, qr_c["y"] + size)
    page.insert_image(qr_rect, stream=qr_png)


def _fill_template_pdf(template_path: str, payload: dict, qr_png: bytes, field_config: dict | None) -> bytes:
    doc = pymupdf.open(template_path)
    if doc.page_count < 1:
        doc.close()
        raise ValueError("Certificate template PDF has no pages.")

    page = doc[0]
    fonts = _pick_fonts(page)

    used_placeholders = False
    used_placeholders |= _replace_placeholder_text(
        page, PLACEHOLDERS["name"], payload["recipient_name"], fonts, fontsize=28, color=PURPLE_DEEP
    )
    used_placeholders |= _replace_placeholder_text(
        page, PLACEHOLDERS["score"], f"{payload['score']}%", fonts, fontsize=20, color=PURPLE_RICH
    )
    used_placeholders |= _replace_placeholder_text(
        page, PLACEHOLDERS["date"], payload["issued_date_display"], fonts, fontsize=12, color=INK
    )
    used_placeholders |= _replace_placeholder_text(
        page,
        PLACEHOLDERS["certificate_id"],
        payload["certificate_id"],
        fonts,
        fontsize=11,
        color=INK,
    )
    used_placeholders |= _place_qr_at_placeholder(page, qr_png)

    if not used_placeholders:
        _overlay_from_config(page, field_config or {}, payload, qr_png, fonts)

    pdf_bytes = doc.tobytes(deflate=True, garbage=3)
    doc.close()
    return pdf_bytes


def _page_size_from_image(image_path: str) -> tuple[float, float]:
    """
    Map image pixel size to PDF points (72 dpi baseline).
    Landscape A4 is used as a max bound so huge photos don't explode the PDF.
    """
    with Image.open(image_path) as img:
        px_w, px_h = img.size
    # 1 image pixel ≈ 1 PDF point at 72dpi; clamp to a printable range.
    width = float(max(400, min(px_w, 1200)))
    height = width * (px_h / px_w) if px_w else 595.0
    height = float(max(280, min(height, 900)))
    return width, height


def _scale_field_config(config: dict | None, src_w: float, src_h: float, dst_w: float, dst_h: float) -> dict:
    """Scale absolute coords from the design's native size into the PDF page size."""
    if not config:
        return {}
    sx = dst_w / src_w if src_w else 1.0
    sy = dst_h / src_h if src_h else 1.0
    scaled = {}
    for key, value in config.items():
        if not isinstance(value, dict):
            continue
        item = dict(value)
        for dim in ("x", "w", "size"):
            if dim in item:
                item[dim] = float(item[dim]) * sx
        for dim in ("y", "h"):
            if dim in item:
                item[dim] = float(item[dim]) * sy
        if "fontsize" in item:
            item["fontsize"] = float(item["fontsize"]) * min(sx, sy)
        scaled[key] = item
    return scaled


def _fill_template_image(template_path: str, payload: dict, qr_png: bytes, field_config: dict | None) -> bytes:
    """Use a JPG/PNG as a full-page background, then overlay dynamic fields."""
    with Image.open(template_path) as img:
        src_w, src_h = img.size

    width, height = _page_size_from_image(template_path)
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    page.insert_image(page.rect, filename=template_path)
    fonts = _pick_fonts(page)

    # If admin configured coords against the image pixel grid, scale them to the page.
    cfg = field_config or {}
    assume_pixels = any(
        isinstance(cfg.get(k), dict) and float(cfg[k].get("x", 0)) > width
        for k in ("name", "score", "date", "certificate_id", "qr")
        if k in cfg
    )
    if assume_pixels:
        cfg = _scale_field_config(cfg, float(src_w), float(src_h), width, height)

    # Default image overlays: proportional boxes when admin left field_config empty.
    if not cfg:
        cfg = {
            "name": {"x": width * 0.1, "y": height * 0.38, "w": width * 0.8, "h": height * 0.1, "fontsize": 36},
            "score": {"x": width * 0.1, "y": height * 0.52, "w": width * 0.8, "h": height * 0.06, "fontsize": 22},
            "date": {"x": width * 0.08, "y": height * 0.82, "w": width * 0.4, "h": height * 0.05, "fontsize": 12},
            "certificate_id": {
                "x": width * 0.08,
                "y": height * 0.88,
                "w": width * 0.45,
                "h": height * 0.05,
                "fontsize": 11,
            },
            "qr": {"x": width * 0.82, "y": height * 0.78, "size": min(width, height) * 0.12},
        }

    _overlay_from_config(page, cfg, payload, qr_png, fonts)
    pdf_bytes = doc.tobytes(deflate=True, garbage=3)
    doc.close()
    return pdf_bytes


def _fill_uploaded_template(template, payload: dict, qr_png: bytes) -> bytes:
    from cyberquest.media_access import stored_file_path

    stored = stored_file_path(template.pdf_file)
    if stored is None:
        raise ValueError("Certificate template file is missing or outside media storage.")
    path = str(stored)
    kind = getattr(template, "template_kind", None)
    if kind is None:
        lower = path.lower()
        kind = "pdf" if lower.endswith(".pdf") else "image"
    config = getattr(template, "field_config", None) or {}
    if kind == "pdf":
        return _fill_template_pdf(path, payload, qr_png, config)
    if kind == "image":
        return _fill_template_image(path, payload, qr_png, config)
    raise ValueError(f"Unsupported certificate template type: {kind}")


def generate_certificate_pdf(
    *,
    recipient_name: str,
    score: int,
    certificate_id: str,
    issued_date_display: str,
    verify_url: str,
    template=None,
    require_template: bool = False,
) -> bytes:
    """
    Generate a certificate PDF once. Returns raw PDF bytes.
    Never trusts client-provided score — caller must pass server values.

    If require_template=True and an uploaded template is provided, failures
    are raised instead of silently falling back to the default design.
    """
    if not (recipient_name or "").strip():
        raise ValueError("Recipient name is required.")
    if score is None or score < 0 or score > 100:
        raise ValueError("Score must be between 0 and 100.")

    payload = {
        "recipient_name": recipient_name.strip(),
        "score": int(score),
        "certificate_id": certificate_id,
        "issued_date_display": issued_date_display,
        "verify_url": verify_url,
    }
    qr_png = make_qr_png_bytes(verify_url)

    if template is not None and getattr(template, "pdf_file", None):
        try:
            return _fill_uploaded_template(template, payload, qr_png)
        except Exception:
            logger.exception(
                "Failed filling uploaded template %s",
                getattr(template, "pk", "?"),
            )
            if require_template:
                raise
            logger.warning("Falling back to default certificate design.")

    return _build_default_pdf(payload, qr_png)
