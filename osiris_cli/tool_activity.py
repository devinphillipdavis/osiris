"""
OSIRIS Tool Activity & Progress Tracking
========================================

Provides visible progress indicators and state tracking across execution turns.
"""

from __future__ import annotations

import sys
import time  # noqa: F401
from enum import Enum
from typing import Optional

from osiris_cli.output_renderer import Colors, OutputRenderer


class ActivityState(str, Enum):
    IDLE = "IDLE"
    READ = "READ"
    SEARCH = "SEARCH"
    PLAN = "PLAN"
    DRAFT = "DRAFT"
    PROPOSED = "PROPOSED"
    WAITING_FOR_APPROVAL = "WAITING FOR APPROVAL"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"


class ToolActivityTracker:
    """Renders real-time activity status in the terminal."""

    def __init__(self, renderer: Optional[OutputRenderer] = None):
        self.renderer = renderer or OutputRenderer()
        self.current_state = ActivityState.IDLE
        self.current_detail = ""

    def set_state(self, state: ActivityState, detail: str = "") -> None:
        self.current_state = state
        self.current_detail = detail
        self.render()

    def render(self) -> None:
        badge = self._format_badge(self.current_state)
        detail = f" {self.current_detail}" if self.current_detail else ""
        sys.stdout.write(f"\r\033[K{badge}{detail}\n")
        sys.stdout.flush()

    def _format_badge(self, state: ActivityState) -> str:
        color_map = {
            ActivityState.READ: Colors.BLUE,
            ActivityState.SEARCH: Colors.CYAN,
            ActivityState.PLAN: Colors.MAGENTA,
            ActivityState.DRAFT: Colors.YELLOW,
            ActivityState.PROPOSED: Colors.BRIGHT_CYAN,
            ActivityState.WAITING_FOR_APPROVAL: Colors.BRIGHT_YELLOW,
            ActivityState.RUNNING: Colors.BLUE,
            ActivityState.PASSED: Colors.GREEN,
            ActivityState.FAILED: Colors.RED,
            ActivityState.BLOCKED_BY_POLICY: Colors.RED,
        }
        col = color_map.get(state, Colors.WHITE)
        return self.renderer.c(col + Colors.BOLD, f"[{state.value}]")
