"""JSON schema helpers for Gemini structured output."""

from __future__ import annotations

from typing import Any


_QUESTION_PROPERTIES: dict[str, Any] = {
    "question_number": {"type": "integer"},
    "question_type": {
        "type": "string",
        "enum": ["mcq", "simulation", "true_false"],
    },
    "question": {"type": "string"},
    "options": {
        "type": "array",
        "items": {"type": "string"},
    },
    "correct_answer": {"type": "string"},
    "explanation": {"type": "string"},
    "difficulty": {
        "type": "string",
        "enum": ["beginner", "intermediate", "advanced"],
    },
    "source_material": {"type": "string"},
    "source_evidence": {"type": "string"},
    "source_excerpt": {"type": "string"},
    "source_section": {"type": "string"},
    "scenario": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "context": {"type": "string"},
            "sender": {"type": "string"},
            "subject": {"type": "string"},
            "body": {"type": "string"},
            "url": {"type": "string"},
            "attachment": {"type": "string"},
            "network_event": {"type": "string"},
            "log_entry": {"type": "string"},
            "alert": {"type": "string"},
            "ip_information": {"type": "string"},
            "traffic_description": {"type": "string"},
            "password_scenario": {"type": "string"},
            "authentication_event": {"type": "string"},
            "login_attempt": {"type": "string"},
            "ciphertext": {"type": "string"},
            "algorithm_scenario": {"type": "string"},
            "key_scenario": {"type": "string"},
            "public_information_scenario": {"type": "string"},
            "source_clues": {"type": "string"},
            "identity_clues": {"type": "string"},
            "metadata": {"type": "string"},
        },
    },
}

_QUESTION_REQUIRED = [
    "question_number",
    "question_type",
    "question",
    "options",
    "correct_answer",
    "explanation",
    "difficulty",
    "source_evidence",
]


GENERATION_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "insufficient_source_content": {
            "type": "boolean",
            "description": "True only when the source cannot support ANY meaningful questions.",
        },
        "message": {
            "type": "string",
            "description": "Human-readable explanation when insufficient_source_content is true.",
        },
        "sets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "set_number": {"type": "integer"},
                    "set_type": {"type": "string", "enum": ["normal", "simulation"]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": _QUESTION_PROPERTIES,
                            "required": _QUESTION_REQUIRED,
                        },
                    },
                },
                "required": ["set_number", "set_type", "title", "questions"],
            },
        },
    },
}


REPAIR_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "insufficient_source_content": {"type": "boolean"},
        "message": {"type": "string"},
        "replacements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    **_QUESTION_PROPERTIES,
                    "set_number": {"type": "integer"},
                },
                "required": ["set_number", *_QUESTION_REQUIRED],
            },
        },
    },
}


def empty_insufficient_payload(message: str) -> dict[str, Any]:
    return {
        "insufficient_source_content": True,
        "message": message,
        "sets": [],
    }
