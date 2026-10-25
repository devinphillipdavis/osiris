"""
OSIRIS REPL Session Manager
===========================

Persistent multi-turn conversation and session state management.
"""

from __future__ import annotations

import json
import os  # noqa: F401
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ConversationTurn:
    turn_id: str
    timestamp: float
    role: str  # "user" or "assistant"
    intent: str
    input_text: str
    output_text: str
    actions_taken: List[Dict[str, Any]] = field(default_factory=list)
    proposed_diffs: List[Dict[str, Any]] = field(default_factory=list)
    approved_by_user: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SessionState:
    session_id: str
    workspace_path: str
    active_mode: str  # chat, inspect, plan, propose, edit, test, research, safe
    active_model: str
    created_at: float
    updated_at: float
    context_files: List[str] = field(default_factory=list)
    turns: List[ConversationTurn] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["turns"] = [t.to_dict() if isinstance(t, ConversationTurn) else t for t in self.turns]
        return d


class SessionManager:
    """Manages session creation, persistence, resumption, and transcript export."""

    def __init__(self, storage_dir: Optional[str] = None):
        if storage_dir:
            self.storage_dir = Path(storage_dir).resolve()
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        else:
            try:
                self.storage_dir = Path.home() / ".osiris" / "sessions"
                self.storage_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.storage_dir = Path("/tmp/.osiris/sessions")
                self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.current_session: Optional[SessionState] = None

    def new_session(
        self,
        workspace_path: str,
        session_id: Optional[str] = None,
        mode: str = "inspect",
        model: str = "local_nclm"
    ) -> SessionState:
        now = time.time()
        sid = session_id or f"session_{int(now)}_{uuid.uuid4().hex[:6]}"
        self.current_session = SessionState(
            session_id=sid,
            workspace_path=str(Path(workspace_path).resolve()),
            active_mode=mode,
            active_model=model,
            created_at=now,
            updated_at=now,
            context_files=[],
            turns=[]
        )
        self.save_session()
        return self.current_session

    def load_session(self, session_id: str) -> Optional[SessionState]:
        file_path = self.storage_dir / f"{session_id}.json"
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        turns = [ConversationTurn(**t) for t in data.get("turns", [])]
        self.current_session = SessionState(
            session_id=data["session_id"],
            workspace_path=data["workspace_path"],
            active_mode=data["active_mode"],
            active_model=data["active_model"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            context_files=data.get("context_files", []),
            turns=turns,
            metadata=data.get("metadata", {})
        )
        return self.current_session

    def save_session(self) -> None:
        if not self.current_session:
            return
        self.current_session.updated_at = time.time()
        file_path = self.storage_dir / f"{self.current_session.session_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.current_session.to_dict(), f, indent=2)

    def add_turn(
        self,
        role: str,
        intent: str,
        input_text: str,
        output_text: str,
        actions_taken: Optional[List[Dict[str, Any]]] = None,
        proposed_diffs: Optional[List[Dict[str, Any]]] = None,
        approved: Optional[bool] = None
    ) -> ConversationTurn:
        if not self.current_session:
            self.new_session(workspace_path=".")

        turn = ConversationTurn(
            turn_id=f"turn_{len(self.current_session.turns) + 1}",
            timestamp=time.time(),
            role=role,
            intent=intent,
            input_text=input_text,
            output_text=output_text,
            actions_taken=actions_taken or [],
            proposed_diffs=proposed_diffs or [],
            approved_by_user=approved
        )
        self.current_session.turns.append(turn)
        self.save_session()
        return turn

    def list_sessions(self) -> List[Dict[str, Any]]:
        sessions = []
        for p in self.storage_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sessions.append({
                        "session_id": data.get("session_id", p.stem),
                        "created_at": data.get("created_at", 0),
                        "updated_at": data.get("updated_at", 0),
                        "workspace": data.get("workspace_path", ""),
                        "mode": data.get("active_mode", ""),
                        "turns_count": len(data.get("turns", []))
                    })
            except Exception:
                continue
        sessions.sort(key=lambda s: s["updated_at"], reverse=True)
        return sessions
