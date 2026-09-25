"""
Per-game question-type configuration for CyberQuest set courses.

question_type and difficulty are independent attributes.
"""

from __future__ import annotations

TYPE_MCQ = "mcq"
TYPE_SIMULATION = "simulation"

# Default play attempt: 5 questions with balanced difficulty (2B+2I+1A)
# and a configurable MCQ/Simulation mix when both types are allowed.
GAME_QUESTION_CONFIG = {
    "phishing_simulator": {
        "allowed_types": (TYPE_MCQ, TYPE_SIMULATION),
        "attempt_size": 5,
        "default_mcq": 2,
        "default_simulation": 3,
        "difficulty_mode": "mixed",
    },
    "password_cracker": {
        "allowed_types": (TYPE_MCQ, TYPE_SIMULATION),
        "attempt_size": 5,
        "default_mcq": 2,
        "default_simulation": 3,
        "difficulty_mode": "mixed",
    },
    "network_defense": {
        "allowed_types": (TYPE_MCQ, TYPE_SIMULATION),
        "attempt_size": 5,
        "default_mcq": 2,
        "default_simulation": 3,
        "difficulty_mode": "mixed",
    },
    "cryptography": {
        # Primarily conceptual MCQs; simulations optional when bank has them.
        "allowed_types": (TYPE_MCQ, TYPE_SIMULATION),
        "attempt_size": 5,
        "default_mcq": 3,
        "default_simulation": 2,
        "difficulty_mode": "mixed",
    },
    "osint": {
        "allowed_types": (TYPE_MCQ, TYPE_SIMULATION),
        "attempt_size": 5,
        "default_mcq": 2,
        "default_simulation": 3,
        "difficulty_mode": "mixed",
    },
}


def get_game_question_config(game_key: str) -> dict:
    return dict(GAME_QUESTION_CONFIG.get(game_key) or {
        "allowed_types": (TYPE_MCQ,),
        "attempt_size": 5,
        "default_mcq": 5,
        "default_simulation": 0,
        "difficulty_mode": "mixed",
    })
