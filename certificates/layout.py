"""Coordinate checks for certificate templates.

The generator uses PDF points measured from the top-left of the page.
Image templates are placed on a PDF page, and the editor saves points on
that page, so a browser resize never changes the stored placement.
"""

from __future__ import annotations

import re

import pymupdf
from django.core.exceptions import ValidationError

from certificates.services.generator import PLACEHOLDERS, page_metrics

def display_to_page(pixel, display_size, page_size):
    """Map a preview pixel to a PDF point. Same ratio the visual builder uses."""
    display_size = float(display_size or 0)
    if display_size <= 0:
        return 0.0
    return round(float(pixel) * float(page_size) / display_size, 1)


FIELD_KEYS = ("name", "score", "date", "certificate_id", "qr")
_NUMBER_KEYS = ("x", "y", "w", "h", "fontsize", "size")
_PLACEHOLDER_TOKEN = re.compile(r"\{\{[A-Z0-9_]+\}\}")
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_field_config(raw) -> dict:
    if raw in (None, "", {}):
        return {}
    if not isinstance(raw, dict):
        raise ValidationError("Field coordinates must be a JSON object.")
    cleaned = {}
    errors = []
    for key, value in raw.items():
        if key not in FIELD_KEYS:
            errors.append(f"Unsupported field '{key}'.")
            continue
        if not isinstance(value, dict):
            errors.append(f"{key} must be an object of coordinates.")
            continue
        item = {}
        for dim in _NUMBER_KEYS:
            if dim not in value or value[dim] in (None, ""):
                continue
            try:
                number = float(value[dim])
            except (TypeError, ValueError):
                errors.append(f"{key}.{dim} must be a number.")
                continue
            if number < 0:
                errors.append(f"{key}.{dim} cannot be negative.")
                continue
            item[dim] = number
        if "align" in value and value["align"] not in (None, ""):
            try:
                align = int(value["align"])
            except (TypeError, ValueError):
                errors.append(f"{key}.align must be 0, 1, or 2.")
            else:
                if align not in (0, 1, 2):
                    errors.append(f"{key}.align must be 0, 1, or 2.")
                else:
                    item["align"] = align
        color = value.get("color")
        if color not in (None, ""):
            if not isinstance(color, str) or not _HEX_COLOR.match(color):
                errors.append(f"{key}.color must be a #RRGGBB color.")
            else:
                item["color"] = color.upper()
        cleaned[key] = item
    if errors:
        raise ValidationError(errors)
    return cleaned


def placeholder_report(path: str, kind: str) -> dict:
    width, height = page_metrics(path, kind)
    found = set()
    unknown = []
    if kind == "pdf":
        doc = pymupdf.open(path)
        try:
            text = doc[0].get_text() if doc.page_count else ""
        finally:
            doc.close()
        found = {key for key, token in PLACEHOLDERS.items() if token in text}
        known = set(PLACEHOLDERS.values())
        unknown = sorted(set(_PLACEHOLDER_TOKEN.findall(text)) - known)
    return {"width": width, "height": height, "placeholders": found, "unknown": unknown}


def fields_outside_page(config: dict, width: float, height: float) -> list[str]:
    problems = []
    for key, item in (config or {}).items():
        if key not in FIELD_KEYS or not isinstance(item, dict):
            continue
        x = float(item.get("x", 0))
        y = float(item.get("y", 0))
        if key == "qr":
            size = float(item.get("size") or item.get("w") or 0)
            right, bottom = x + size, y + size
        else:
            right = x + float(item.get("w") or 0)
            bottom = y + float(item.get("h") or 0)
        if x < -1 or y < -1 or right > width + 1 or bottom > height + 1:
            problems.append(f"{key} extends outside the page.")
    return problems


def missing_overlay_fields(config: dict, placeholders: set[str]) -> list[str]:
    missing = []
    for key in FIELD_KEYS:
        if key in placeholders:
            continue
        item = (config or {}).get(key) or {}
        if key == "qr":
            ready = "x" in item and "y" in item and ("size" in item or "w" in item)
        else:
            ready = all(dim in item for dim in ("x", "y", "w", "h"))
        if not ready:
            missing.append(key)
    return missing


def activation_errors(path: str, kind: str, config: dict) -> list[str]:
    report = placeholder_report(path, kind)
    errors = [f"Unsupported placeholder {token}." for token in report["unknown"]]
    overlay = {
        key: value for key, value in (config or {}).items()
        if key not in report["placeholders"]
    }
    errors.extend(fields_outside_page(overlay, report["width"], report["height"]))
    missing = missing_overlay_fields(config, report["placeholders"])
    if missing and not report["placeholders"]:
        errors.append(
            "Set coordinates for " + ", ".join(missing) + " before activating this template."
        )
    elif missing:
        errors.append(
            "These fields have no placeholder and no coordinates: " + ", ".join(missing) + "."
        )
    return errors
