"""Lightweight source-grounding checks for generated questions."""

from __future__ import annotations

import re


_TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)


def tokenize(text: str) -> set[str]:
    return {t.casefold() for t in _TOKEN_RE.findall(text or "") if len(t) > 2}


def evidence_appears_grounded(source_content: str, evidence: str, *, min_overlap: int = 2) -> bool:
    """
    Require a small lexical overlap between evidence and source.

    Missing evidence fails elsewhere; this only rejects evidence that looks
    completely unrelated to the supplied source.
    """
    evidence = (evidence or "").strip()
    if not evidence:
        return False
    source_tokens = tokenize(source_content)
    evidence_tokens = tokenize(evidence)
    if not evidence_tokens:
        return False
    # Very short sources: accept any non-empty evidence.
    if len(source_tokens) < 8:
        return True
    overlap = source_tokens & evidence_tokens
    return len(overlap) >= min(min_overlap, len(evidence_tokens))


def estimate_source_capacity(source_content: str, expected_questions: int) -> tuple[bool, str]:
    """
    Advisory heuristic only — MUST NOT hard-fail generation.

    Short sources can still yield valid questions if they contain enough
    distinct educational material. Returns (True, note) always for gating
    purposes; the note may warn about thin content.
    """
    text = (source_content or "").strip()
    words = len(text.split())
    soft_floor = max(40, expected_questions * 5)
    if words < soft_floor:
        return True, (
            f"Source is relatively short (~{words} words for "
            f"{expected_questions} requested questions). Generation will proceed; "
            "quality depends on distinct concepts in the material."
        )
    return True, ""
