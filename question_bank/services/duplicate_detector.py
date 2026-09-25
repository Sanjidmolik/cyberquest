"""Duplicate detection for generated question text."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def normalize_question_text(text: str) -> str:
    """Lowercase, strip, remove punctuation, collapse whitespace."""
    value = unicodedata.normalize("NFKC", text or "")
    value = value.casefold().strip()
    value = _PUNCT_RE.sub(" ", value)
    value = _SPACE_RE.sub(" ", value).strip()
    return value


def similarity_ratio(a: str, b: str) -> float:
    na = normalize_question_text(a)
    nb = normalize_question_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def find_duplicates(
    questions: list[str],
    *,
    near_threshold: float = 0.88,
) -> list[dict]:
    """
    Return list of duplicate findings:
    [{"index_a": i, "index_b": j, "kind": "exact"|"near", "ratio": float, "text_a": ..., "text_b": ...}]
    """
    findings: list[dict] = []
    normalized = [normalize_question_text(q) for q in questions]
    for i in range(len(questions)):
        for j in range(i + 1, len(questions)):
            if not normalized[i] or not normalized[j]:
                continue
            if normalized[i] == normalized[j]:
                findings.append({
                    "index_a": i,
                    "index_b": j,
                    "kind": "exact",
                    "ratio": 1.0,
                    "text_a": questions[i],
                    "text_b": questions[j],
                })
                continue
            ratio = SequenceMatcher(None, normalized[i], normalized[j]).ratio()
            if ratio >= near_threshold:
                findings.append({
                    "index_a": i,
                    "index_b": j,
                    "kind": "near",
                    "ratio": ratio,
                    "text_a": questions[i],
                    "text_b": questions[j],
                })
    return findings
