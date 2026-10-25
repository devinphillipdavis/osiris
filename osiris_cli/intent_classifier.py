"""
OSIRIS Conversational Intent Classifier
=======================================

Deterministic, local classifier mapping natural language user prompts to core engineering intents.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401


class UserIntent(str, Enum):
    EXPLAIN = "EXPLAIN"
    DEBUG = "DEBUG"
    PLAN = "PLAN"
    EDIT = "EDIT"
    REVIEW = "REVIEW"
    SEARCH = "SEARCH"
    RESEARCH = "RESEARCH"
    COMMAND = "COMMAND"
    CHAT = "CHAT"


class IntentClassifier:
    """Classifies user inputs into structured operational intents."""

    PATTERNS = [
        (UserIntent.COMMAND, r"^\s*/[a-zA-Z0-9_\-]+"),
        (UserIntent.RESEARCH, r"\b(hypothesis|hypotheses|preregister|experiment|simulate|rubric|null hypothesis|claim ceiling)\b"),
        (UserIntent.DEBUG, r"\b(debug|fix|bug|error|exception|traceback|syntaxerror|typeerror|failed|failure|crash)\b"),
        (UserIntent.PLAN, r"\b(plan|roadmap|steps|how to implement|design proposal|architect|strategy)\b"),
        (UserIntent.EDIT, r"\b(edit|modify|refactor|update|change|rewrite|add function|patch|implement)\b"),
        (UserIntent.REVIEW, r"\b(review|audit|diff|check security|verify|sanity check|critique|inspect changes)\b"),
        (UserIntent.SEARCH, r"\b(find|search|where is|locate|grep|show file|list all)\b"),
        (UserIntent.EXPLAIN, r"\b(explain|what is|what does|how does|walkthrough|describe|clarify|tell me about)\b"),
    ]

    @classmethod
    def classify(cls, text: str) -> Tuple[UserIntent, float]:
        """Returns the classified UserIntent and a confidence score between 0.0 and 1.0."""
        text_lower = text.strip().lower()

        if text_lower.startswith("/"):
            return UserIntent.COMMAND, 1.0

        for intent, pattern in cls.PATTERNS:
            if re.search(pattern, text_lower):
                return intent, 0.85

        return UserIntent.CHAT, 0.50
