"""
OSIRIS Human Approval UI
========================

Prompts for human confirmation on privileged actions, diffs, and execution requests.
"""

from __future__ import annotations

import sys  # noqa: F401
from typing import Callable, Optional

from osiris_cli.output_renderer import Colors, OutputRenderer  # noqa: F401


class ApprovalUI:
    """Handles confirmation prompts for actions, diffs, and executions."""

    def __init__(self, renderer: Optional[OutputRenderer] = None):
        self.renderer = renderer or OutputRenderer()

    def prompt_confirmation(
        self,
        action_description: str,
        diff_callback: Optional[Callable[[], None]] = None,
        default: str = "n"
    ) -> bool:
        """
        Interactive prompt:
        Accept action? [y/N/d/q] (yes, no, view diff, quit)
        """
        prompt_str = self.renderer.yellow(f"\n❓ {action_description}\nConfirm execution [y/N/d/q]: ")

        while True:
            try:
                choice = input(prompt_str).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return False

            if not choice:
                choice = default

            if choice in ("y", "yes"):
                return True
            elif choice in ("n", "no"):
                return False
            elif choice in ("q", "quit"):
                print(self.renderer.dim("Aborted by user."))
                return False
            elif choice in ("d", "diff"):
                if diff_callback:
                    diff_callback()
                else:
                    print(self.renderer.dim("No diff available for this action."))
            else:
                print(self.renderer.dim("Please enter 'y', 'n', 'd', or 'q'."))

    def prompt_human_token(self, prompt_text: str) -> Optional[str]:
        """Prompt user for explicit human approval token required by OCCR gates."""
        print(self.renderer.yellow(f"\n🔒 {prompt_text}"))
        try:
            token = input(self.renderer.bold("Enter approval token (or empty to cancel): ")).strip()
            return token if token else None
        except (EOFError, KeyboardInterrupt):
            print()
            return None
