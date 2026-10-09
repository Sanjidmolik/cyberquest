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
    "name": {"x": 80, "y": 230, "w": 682, "h": 56, "fontsize": 36, "align": 1, "color": "#520EA3"},
    "score": {"x": 80, "y": 320, "w": 682, "h": 36, "fontsize": 22, "align": 1, "color": "#701FD3"},
    "date": {"x": 80, "y": 480, "w": 320, "h": 28, "fontsize": 12, "align": 0, "color": "#1B1030"},
    "certificate_id": {"x": 80, "y": 508, "w": 320, "h": 28, "fontsize": 11, "align": 0, "color": "#1B1030"},
    "qr": {"x": 700, "y": 460, "size": 90},
}

# Measured on CyberQuest_Certificate_of_Achievement.pdf (A4 landscape, origin top-left, PDF points).
# The recipient line is y=306.8; the intro sentence ends at y=252.8.
ACHIEVEMENT_FIELD_CONFIG = {
    "name": {"x": 169, "y": 280, "w": 504, "h": 26, "fontsize": 20, "align": 1, "color": "#F4EEFF"},
    "score": {"x": 400, "y": 351, "w": 42, "h": 18, "fontsize": 13, "align": 1, "color": "#FFFFFF"},
    "date": {"x": 338, "y": 504, "w": 210, "h": 18, "fontsize": 9, "align": 0, "color": "#D1C7F5"},
    "certificate_id": {"x": 92, "y": 504, "w": 176, "h": 18, "fontsize": 9, "align": 0, "color": "#D1C7F5"},
    "qr": {"x": 564.5, "y": 485.5, "size": 35},
}
ACHIEVEMENT_TEMPLATE_NAME = "CyberQuest_Certificate_of_Achievement.pdf"

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


def builtin_achievement_template() -> Path:
    """Permanent CyberQuest Certificate of Achievement design."""
    return (
        Path(settings.BASE_DIR)
        / "media"
        / "certificate_templates"
        / "CyberQuest_Certificate_of_Achievement.pdf"
    )


def pdf_bytes_to_png(pdf_bytes: bytes, zoom: float = 2.0) -> bytes:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.page_count < 1:
            raise ValueError("Certificate PDF has no pages.")
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def _fill_achievement_template(template_path: str, payload: dict, qr_png: bytes, field_config: dict | None = None) -> bytes:
    """
    Stamp the permanent dark certificate. Coordinates are PDF points from the
    top-left of CyberQuest_Certificate_of_Achievement.pdf (A4 landscape).
    A blank certificate id is a live learner preview: name and score only.
    Saved field_config overrides the measured defaults field by field.
    """
    doc = pymupdf.open(template_path)
    try:
        if doc.page_count < 1:
            raise ValueError("Certificate template PDF has no pages.")
        page = doc[0]
        score_cover = (34 / 255, 18 / 255, 62 / 255)
        hits = page.search_for("__%")
        for rect in hits:
            pad = pymupdf.Rect(rect.x0 - 2, rect.y0 - 1, rect.x1 + 6, rect.y1 + 1)
            page.add_redact_annot(pad, fill=score_cover)
        if hits:
            page.apply_redactions(images=0)
        else:
            page.draw_circle(pymupdf.Point(421, 360), 16, color=None, fill=score_cover)

        fonts = _pick_fonts(page)
        cfg = _merge_field_config(ACHIEVEMENT_FIELD_CONFIG, field_config)
        _draw_configured_fields(
            page, cfg, payload, qr_png, fonts,
            keys={"name", "score", "date", "certificate_id"},
        )
        if (payload.get("certificate_id") or "").strip() and (payload.get("verify_url") or "").strip() and qr_png:
            spec = cfg["qr"]
            size = float(spec.get("size") or 35)
            qr_rect = pymupdf.Rect(float(spec["x"]), float(spec["y"]), float(spec["x"]) + size, float(spec["y"]) + size)
            page.draw_rect(qr_rect, color=None, fill=(1, 1, 1))
            page.insert_image(qr_rect, stream=qr_png)

        pdf_bytes = doc.tobytes(deflate=True, garbage=3)
    finally:
        doc.close()
    return pdf_bytes


def _build_default_pdf(payload: dict, qr_png: bytes) -> bytes:
    template = builtin_achievement_template()
    if template.is_file():
        return _fill_achievement_template(str(template), payload, qr_png)
    return _build_legacy_default_pdf(payload, qr_png)


def _build_legacy_default_pdf(payload: dict, qr_png: bytes) -> bytes:
    # Landscape A4 in points — used only if the permanent template file is missing.
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


def _redact_placeholder(page, needle: str):
    hits = page.search_for(needle)
    for rect in hits:
        page.add_redact_annot(rect, fill=PAPER)
    return hits


def _replace_placeholder_text(page, needle: str, replacement: str, fonts, fontsize=16, color=INK):
    hits = _redact_placeholder(page, needle)
    if hits:
        page.apply_redactions(images=0)
    for rect in hits:
        grow = max(0, len(replacement) - len(needle)) * (fontsize * 0.28)
        box = pymupdf.Rect(rect.x0 - grow / 2, rect.y0 - 2, rect.x1 + grow / 2 + 40, rect.y1 + 4)
        box = box & page.rect
        _fit_textbox(page, box, replacement, fonts["bold"], fontsize, min_size=8, color=color, align=1)
    return bool(hits)


def _place_qr_at_placeholder(page, qr_png: bytes):
    hits = _redact_placeholder(page, PLACEHOLDERS["qr"])
    if hits:
        page.apply_redactions(images=0)
    for rect in hits:
        size = max(rect.width, rect.height, 70)
        qr_rect = pymupdf.Rect(rect.x0, rect.y0, rect.x0 + size, rect.y0 + size)
        page.insert_image(qr_rect, stream=qr_png)
    return bool(hits)


def _merge_field_config(base: dict, override: dict | None) -> dict:
    merged = {key: dict(value) for key, value in base.items()}
    if not isinstance(override, dict):
        return merged
    for key, value in override.items():
        if isinstance(value, dict):
            merged[key] = {**merged.get(key, {}), **value}
    return merged


def _rgb(value, fallback):
    if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
        try:
            return tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))
        except ValueError:
            return fallback
    return fallback


def _box(spec: dict, width_key="w", height_key="h"):
    x = float(spec.get("x", 0))
    y = float(spec.get("y", 0))
    return pymupdf.Rect(x, y, x + float(spec.get(width_key, 0)), y + float(spec.get(height_key, 0)))


def _draw_configured_fields(page, config: dict, payload: dict, qr_png: bytes, fonts, *, keys=None):
    """Draw overlay fields. Coordinates are PDF points from the top-left."""
    selected = set(keys) if keys is not None else set(config)
    if "name" in selected and config.get("name"):
        spec = config["name"]
        _fit_textbox(
            page,
            _box(spec),
            payload["recipient_name"],
            fonts["display"],
            max_size=float(spec.get("fontsize", 28)),
            min_size=8,
            color=_rgb(spec.get("color"), PURPLE_DEEP),
            align=int(spec.get("align", 1)),
        )
    if "score" in selected and config.get("score"):
        spec = config["score"]
        _fit_textbox(
            page,
            _box(spec),
            f"{payload['score']}%",
            fonts["bold"],
            max_size=float(spec.get("fontsize", 16)),
            min_size=7,
            color=_rgb(spec.get("color"), PURPLE_RICH),
            align=int(spec.get("align", 1)),
        )
    if "date" in selected and config.get("date") and (payload.get("issued_date_display") or "").strip():
        spec = config["date"]
        _fit_textbox(
            page,
            _box(spec),
            payload["issued_date_display"],
            fonts["regular"],
            max_size=float(spec.get("fontsize", 12)),
            min_size=7,
            color=_rgb(spec.get("color"), INK),
            align=int(spec.get("align", 0)),
        )
    if "certificate_id" in selected and config.get("certificate_id") and (payload.get("certificate_id") or "").strip():
        spec = config["certificate_id"]
        _fit_textbox(
            page,
            _box(spec),
            payload["certificate_id"],
            fonts["regular"],
            max_size=float(spec.get("fontsize", 11)),
            min_size=7,
            color=_rgb(spec.get("color"), INK),
            align=int(spec.get("align", 0)),
        )
    verify_url = (payload.get("verify_url") or "").strip()
    if "qr" in selected and config.get("qr") and qr_png and verify_url and (payload.get("certificate_id") or "").strip():
        spec = config["qr"]
        size = float(spec.get("size") or spec.get("w") or 90)
        rect = pymupdf.Rect(float(spec["x"]), float(spec["y"]), float(spec["x"]) + size, float(spec["y"]) + size)
        page.insert_image(rect, stream=qr_png)


def _overlay_from_config(page, config: dict, payload: dict, qr_png: bytes, fonts, *, keys=None):
    cfg = _merge_field_config(DEFAULT_FIELD_CONFIG, config)
    _draw_configured_fields(page, cfg, payload, qr_png, fonts, keys=keys)


def _fill_template_pdf(template_path: str, payload: dict, qr_png: bytes, field_config: dict | None) -> bytes:
    doc = pymupdf.open(template_path)
    if doc.page_count < 1:
        doc.close()
        raise ValueError("Certificate template PDF has no pages.")

    page = doc[0]
    placed = set()
    replacements = {
        "name": (payload["recipient_name"], 28, PURPLE_DEEP),
        "score": (f"{payload['score']}%", 20, PURPLE_RICH),
        "date": (payload.get("issued_date_display") or "", 12, INK),
        "certificate_id": (payload.get("certificate_id") or "", 11, INK),
    }
    pending = []
    for key, (text, size, color) in replacements.items():
        if not text:
            continue
        hits = _redact_placeholder(page, PLACEHOLDERS[key])
        if hits:
            pending.append((key, text, size, color, hits))
            placed.add(key)
    qr_hits = []
    if (payload.get("verify_url") or "").strip() and qr_png:
        qr_hits = _redact_placeholder(page, PLACEHOLDERS["qr"])
        if qr_hits:
            placed.add("qr")
    if pending or qr_hits:
        page.apply_redactions(images=0)
    # Redaction drops embedded fonts, so fonts are chosen after it.
    fonts = _pick_fonts(page)
    for key, text, size, color, hits in pending:
        for rect in hits:
            grow = max(0, len(text) - len(PLACEHOLDERS[key])) * (size * 0.28)
            box = pymupdf.Rect(rect.x0 - grow / 2, rect.y0 - 2, rect.x1 + grow / 2 + 40, rect.y1 + 4)
            box = box & page.rect
            _fit_textbox(page, box, text, fonts["bold"], size, min_size=8, color=color, align=1)
    for rect in qr_hits:
        size = max(rect.width, rect.height, 70)
        page.insert_image(pymupdf.Rect(rect.x0, rect.y0, rect.x0 + size, rect.y0 + size), stream=qr_png)

    missing = [key for key in ("name", "score", "date", "certificate_id", "qr") if key not in placed]
    if missing:
        _overlay_from_config(page, field_config or {}, payload, qr_png, fonts, keys=missing)

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


def is_achievement_template(path: str) -> bool:
    return path.replace("\\", "/").endswith(ACHIEVEMENT_TEMPLATE_NAME)


def page_metrics(path: str, kind: str) -> tuple[float, float]:
    """PDF-point page size the generator will draw on. Origin is the top-left."""
    if kind == "pdf":
        doc = pymupdf.open(path)
        try:
            if doc.page_count < 1:
                raise ValueError("Certificate template PDF has no pages.")
            rect = doc[0].rect
            return float(rect.width), float(rect.height)
        finally:
            doc.close()
    return _page_size_from_image(path)


def editor_field_config(path: str, kind: str, saved: dict | None) -> dict:
    """Config shown in the visual editor. Empty saves use the same defaults as generation."""
    if kind == "pdf" and is_achievement_template(path):
        return _merge_field_config(ACHIEVEMENT_FIELD_CONFIG, saved)
    if saved:
        return _merge_field_config(DEFAULT_FIELD_CONFIG, saved)
    width, height = page_metrics(path, kind)
    if kind == "image":
        return {
            "name": {"x": width * 0.1, "y": height * 0.38, "w": width * 0.8, "h": height * 0.1, "fontsize": 36, "align": 1, "color": "#520EA3"},
            "score": {"x": width * 0.1, "y": height * 0.52, "w": width * 0.8, "h": height * 0.06, "fontsize": 22, "align": 1, "color": "#701FD3"},
            "date": {"x": width * 0.08, "y": height * 0.82, "w": width * 0.4, "h": height * 0.05, "fontsize": 12, "align": 0, "color": "#1B1030"},
            "certificate_id": {"x": width * 0.08, "y": height * 0.88, "w": width * 0.45, "h": height * 0.05, "fontsize": 11, "align": 0, "color": "#1B1030"},
            "qr": {"x": width * 0.82, "y": height * 0.78, "size": min(width, height) * 0.12},
        }
    return _merge_field_config(DEFAULT_FIELD_CONFIG, None)


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
        if path.replace("\\", "/").endswith(ACHIEVEMENT_TEMPLATE_NAME):
            return _fill_achievement_template(path, payload, qr_png, config)
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
