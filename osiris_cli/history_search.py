"""
OSIRIS Conversation History Search
==================================

Search previous session turns, user queries, and assistant responses.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional  # noqa: F401

from osiris_cli.session_manager import ConversationTurn, SessionState


class HistorySearch:
    """Searches conversation history by keyword, intent, or timestamp."""

    @staticmethod
    def search(session: SessionState, query: str) -> List[ConversationTurn]:
        q = query.lower().strip()
        matches = []
        for turn in session.turns:
            if q in turn.input_text.lower() or q in turn.output_text.lower() or q in turn.intent.lower():
                matches.append(turn)
        return matches

    @staticmethod
    def get_last_n(session: SessionState, n: int = 5) -> List[ConversationTurn]:
        return session.turns[-n:] if session.turns else []
