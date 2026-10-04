"""
Target-language checks for generated question text.

English detection is based on Latin function words plus negative signals
for Hindi (Devanagari and distinctive romanized Hindi words). A lone
cybersecurity acronym, URL, or short technical token is not enough to
reject a question. Bangla source quotes in source_evidence are ignored.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z']{2,}")

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_BENGALI_RE = re.compile(r"[\u0980-\u09FF]")

_ENGLISH_FUNCTION = {
    "a", "an", "the", "of", "to", "and", "or", "but", "is", "are", "was",
    "were", "be", "been", "being", "for", "in", "on", "with", "that", "this",
    "these", "those", "which", "who", "you", "your", "from", "not", "if",
    "as", "by", "it", "its", "should", "must", "do", "does", "can", "will",
    "has", "have", "when", "what", "why", "how", "into", "about", "after",
    "before", "because", "than", "then", "their", "they", "user", "users",
}

# Whole words that are distinctive in romanized Hindi and unlikely in
# English cybersecurity prose. Short tokens (ke, ka, ki) are omitted.
_HINDI_ROMAN = {
    "aapka", "aapke", "aapki", "aapko", "kya", "kyon", "kyun", "kaun",
    "nahi", "nahin", "hain", "isliye", "kyunki", "lekin", "chuniye",
    "prashn", "sawal", "uttar", "galat", "dwara", "yeh", "yah", "woh",
    "uska", "iska", "hamara", "tumhara", "kijiye", "bataiye", "vyakhya",
    "hai",
}

# Student-facing scenario keys. Artifact fields (url, raw email) stay unchecked
# so a simulated phishing link does not fail language validation.
_SCENARIO_TEXT_KEYS = {
    "title", "body", "instructions", "instruction", "feedback", "hint",
    "hints", "explanation", "prompt", "question", "description",
    "correct_feedback", "wrong_feedback", "evaluation", "action_feedback",
}

_SKIP_SCENARIO_KEYS = {
    "url", "link", "href", "ip", "ip_address", "sender_email", "email",
}


def language_errors_for_question(
    question: dict[str, Any],
    *,
    target_language: str,
    tag: str,
) -> list[str]:
    """
    Return validation errors when student-facing text is not the target language.

    Clear mismatches and ambiguous cases both fail so the slot can be repaired.
    Too-short technical fields (acronyms, single letters) are skipped.
    """
    target = (target_language or "en").strip().lower()
    if target in {"same_as_source", ""}:
        target = "en"

    errors: list[str] = []
    for label, text in _student_facing_strings(question):
        verdict = classify_text(text, target)
        if verdict == "ok" or verdict == "insufficient":
            continue
        if verdict == "mismatch":
            message = (
                f"{tag}: {label} is not { _target_name(target) } "
                f"(language mismatch)."
            )
        else:
            message = (
                f"{tag}: {label} language is ambiguous for target "
                f"{_target_name(target)}; regenerate in that language only."
            )
        logger.warning(
            "Language validation failed slot=%s field=%s target=%s verdict=%s",
            tag,
            label,
            target,
            verdict,
        )
        errors.append(message)
    return errors


def classify_text(text: str, target_language: str) -> str:
    """
    Return ok, mismatch, ambiguous, or insufficient.

    insufficient means the string has too little natural language to judge
    (acronym, URL, single letter) and must not cause a rejection.
    """
    target = (target_language or "en").strip().lower()
    raw = text or ""
    cleaned = _URL_RE.sub(" ", raw)
    dev = len(_DEVANAGARI_RE.findall(cleaned))
    bn = len(_BENGALI_RE.findall(cleaned))
    words = [w.lower() for w in _WORD_RE.findall(cleaned)]
    english_hits = sum(1 for w in words if w in _ENGLISH_FUNCTION)
    hindi_hits = sum(1 for w in words if w in _HINDI_ROMAN)
    letters = dev + bn + sum(len(w) for w in words)
    if letters < 3 and dev == 0 and bn == 0:
        return "insufficient"

    if target == "bn":
        return _classify_bangla(
            dev=dev, bn=bn, english_hits=english_hits, words=words, letters=letters,
        )
    return _classify_english(
        dev=dev,
        bn=bn,
        english_hits=english_hits,
        hindi_hits=hindi_hits,
        words=words,
        letters=letters,
    )


def _classify_english(
    *,
    dev: int,
    bn: int,
    english_hits: int,
    hindi_hits: int,
    words: list[str],
    letters: int,
) -> str:
    if dev >= 20 or (letters and dev / max(letters, 1) >= 0.2 and dev >= 10):
        return "mismatch"
    if hindi_hits >= 2 and hindi_hits >= english_hits:
        return "mismatch"
    if hindi_hits >= 1 and english_hits == 0 and len(words) >= 4:
        return "mismatch"
    if bn >= 15 and letters and bn / letters >= 0.4:
        return "mismatch"
    # A short Devanagari fragment mixed into otherwise English prose.
    if dev >= 8 and english_hits >= 1:
        return "ambiguous"
    if bn >= 8 and english_hits >= 1 and letters and 0.25 <= bn / letters < 0.4:
        return "ambiguous"
    if english_hits >= 1:
        return "ok"
    if hindi_hits == 0 and dev < 8 and bn < 8:
        # Acronyms and technical word lists are valid English output.
        return "ok" if words or letters < 12 else "insufficient"
    if not words and dev == 0 and bn == 0:
        return "insufficient"
    return "ambiguous"


def _classify_bangla(
    *,
    dev: int,
    bn: int,
    english_hits: int,
    words: list[str],
    letters: int,
) -> str:
    if dev >= 12:
        return "mismatch"
    if bn >= 8 and (not letters or bn / letters >= 0.3 or english_hits <= 4):
        return "ok"
    if english_hits >= 3 and bn < 4:
        return "mismatch"
    if bn >= 4 and english_hits <= 2:
        return "ok"
    if len(words) <= 3 and bn == 0 and dev == 0:
        return "insufficient"
    if bn == 0 and english_hits == 0 and words:
        return "insufficient"
    return "ambiguous"


def _student_facing_strings(question: dict[str, Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    prompt = str(question.get("question") or "").strip()
    if prompt:
        pairs.append(("question", prompt))
    explanation = str(question.get("explanation") or "").strip()
    if explanation:
        pairs.append(("explanation", explanation))
    options = question.get("options") or []
    if isinstance(options, list):
        for i, opt in enumerate(options, start=1):
            text = str(opt or "").strip()
            if text:
                pairs.append((f"option {i}", text))
    scenario = question.get("scenario")
    if isinstance(scenario, dict):
        pairs.extend(_scenario_strings(scenario))
    return pairs


def _scenario_strings(scenario: dict[str, Any], prefix: str = "scenario") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for key, value in scenario.items():
        key_name = str(key)
        if key_name in _SKIP_SCENARIO_KEYS:
            continue
        path = f"{prefix}.{key_name}"
        if isinstance(value, str) and value.strip() and key_name in _SCENARIO_TEXT_KEYS:
            found.append((path, value.strip()))
        elif isinstance(value, dict):
            found.extend(_scenario_strings(value, path))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip() and key_name in _SCENARIO_TEXT_KEYS:
                    found.append((path, item.strip()))
                elif isinstance(item, dict):
                    found.extend(_scenario_strings(item, path))
    return found


def _target_name(target: str) -> str:
    return {"en": "English", "bn": "Bangla"}.get(target, target)
