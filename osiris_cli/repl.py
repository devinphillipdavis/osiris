"""
OSIRIS Interactive REPL Loop
============================

Terminal interactive REPL enforcing the deterministic prompt contract:
`osiris::}{> `
"""

from __future__ import annotations

import os  # noqa: F401
import readline
import sys  # noqa: F401
from pathlib import Path
from typing import Optional

from osiris_cli.conversation_router import ConversationRouter
from osiris_cli.output_renderer import Colors, OutputRenderer
from osiris_cli.session_manager import SessionManager


class OsirisREPL:
    """The interactive conversational shell for OSIRIS."""

    PROMPT = "osiris::}{> "

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        session_id: Optional[str] = None,
        mode: str = "inspect",
        model: str = "local_nclm"
    ):
        self.workspace_root = Path(workspace_root or ".").resolve()
        self.session_manager = SessionManager()
        self.session = self.session_manager.new_session(
            workspace_path=str(self.workspace_root),
            session_id=session_id,
            mode=mode,
            model=model
        )
        self.renderer = OutputRenderer()
        self.router = ConversationRouter(
            workspace_root=str(self.workspace_root),
            session_manager=self.session_manager,
            renderer=self.renderer
        )
        self._setup_readline()

    def _setup_readline(self) -> None:
        hist_dir = Path.home() / ".osiris"
        hist_dir.mkdir(parents=True, exist_ok=True)
        self.hist_file = hist_dir / "repl_history"
        try:
            if self.hist_file.exists():
                readline.read_history_file(str(self.hist_file))
            readline.set_history_length(1000)
        except Exception:
            pass

    def _save_readline(self) -> None:
        try:
            readline.write_history_file(str(self.hist_file))
        except Exception:
            pass

    def run(self) -> int:
        """Start the interactive REPL session."""
        # 1. Print Startup Header Box
        banner = self.renderer.render_header_box(
            workspace=self.workspace_root.name,
            session=self.session.session_id,
            mode=self.session.active_mode,
            model=self.session.active_model,
            policy="READ/PROPOSE",
            context_files_count=len(self.router.context_resolver.list_files())
        )
        print(banner)
        print(self.renderer.dim("Type /help for command documentation, /exit to quit.\n"))

        while True:
            try:
                # The terminal prompt MUST strictly format as 'osiris::}{> '
                prompt_text = self.renderer.c(Colors.BRIGHT_CYAN + Colors.BOLD, self.PROMPT) if self.renderer.color_enabled else self.PROMPT
                user_input = input(prompt_text).strip()

                if not user_input:
                    continue

                if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
                    print(self.renderer.dim("Exiting OSIRIS REPL."))
                    break

                response = self.router.route_turn(user_input)
                if response:
                    print(response)
                    print()

                # Record turn in session
                self.session_manager.add_turn(
                    role="user",
                    intent="INTERACTION",
                    input_text=user_input,
                    output_text=response
                )

            except (KeyboardInterrupt, EOFError):
                print(self.renderer.dim("\nSession terminated."))
                break
            except Exception as ex:
                print(self.renderer.red(f"\n[Error] {str(ex)}\n"))

        self._save_readline()
        return 0
