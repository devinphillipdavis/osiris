"""
OSIRIS Terminal Output Renderer
===============================

Clean, robust ANSI formatting, box-drawing, and table rendering for terminal REPL.
"""

from __future__ import annotations

import os  # noqa: F401
import sys
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401


class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # Standard colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Backgrounds
    BG_BLUE = "\033[44m"
    BG_DARK_GRAY = "\033[100m"


class OutputRenderer:
    """Renders formatted terminal output with colors and box characters."""

    def __init__(self, color_enabled: bool = True):
        self.color_enabled = color_enabled and sys.stdout.isatty()

    def c(self, color_code: str, text: str) -> str:
        if not self.color_enabled:
            return text
        return f"{color_code}{text}{Colors.RESET}"

    def bold(self, text: str) -> str:
        return self.c(Colors.BOLD, text)

    def dim(self, text: str) -> str:
        return self.c(Colors.DIM, text)

    def cyan(self, text: str) -> str:
        return self.c(Colors.CYAN, text)

    def green(self, text: str) -> str:
        return self.c(Colors.GREEN, text)

    def yellow(self, text: str) -> str:
        return self.c(Colors.YELLOW, text)

    def red(self, text: str) -> str:
        return self.c(Colors.RED, text)

    def magenta(self, text: str) -> str:
        return self.c(Colors.MAGENTA, text)

    def render_header_box(
        self,
        workspace: str,
        session: str,
        mode: str,
        model: str,
        policy: str,
        context_files_count: int,
        width: int = 76
    ) -> str:
        """
        Renders the canonical top header banner:
        ┌─ OSIRIS ─ workspace: <repo> ─ session: <name> ─ mode: LOCAL ─────────┐
        │ Model: <active adapter>   Policy: READ/PROPOSE   Context: <N files>   │
        └───────────────────────────────────────────────────────────────────────┘
        """
        line1_content = f" OSIRIS ─ workspace: {workspace} ─ session: {session} ─ mode: {mode} "
        dash_count = max(0, width - 2 - len(line1_content))
        top_line = f"┌─{line1_content}{'─' * dash_count}┐"

        line2_content = f" Model: {model}   Policy: {policy}   Context: {context_files_count} files"
        space_count = max(0, width - 2 - len(line2_content))
        mid_line = f"│{line2_content}{' ' * space_count}│"

        bot_line = f"└{'─' * (width - 2)}┘"

        if self.color_enabled:
            top_line = self.c(Colors.CYAN, top_line)
            mid_line = f"{self.c(Colors.CYAN, '│')} {self.bold('Model:')} {self.green(model)}   {self.bold('Policy:')} {self.yellow(policy)}   {self.bold('Context:')} {self.cyan(str(context_files_count) + ' files')}{' ' * max(0, width - 2 - len(line2_content) - 1)}{self.c(Colors.CYAN, '│')}"
            bot_line = self.c(Colors.CYAN, bot_line)

        return f"{top_line}\n{mid_line}\n{bot_line}"

    def render_alert(self, level: str, title: str, message: str) -> str:
        """Render a GitHub-style alert block (NOTE, TIP, IMPORTANT, WARNING, CAUTION)."""
        color_map = {
            "NOTE": Colors.BLUE,
            "TIP": Colors.GREEN,
            "IMPORTANT": Colors.MAGENTA,
            "WARNING": Colors.YELLOW,
            "CAUTION": Colors.RED,
        }
        col = color_map.get(level.upper(), Colors.CYAN)
        prefix = f"[{level.upper()}] {title}" if title else f"[{level.upper()}]"
        header = self.c(col + Colors.BOLD, f"> {prefix}")
        body = "\n".join(f"> {line}" for line in message.splitlines())
        return f"{header}\n{body}"

    def render_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """Render a clean ASCII table."""
        if not headers and not rows:
            return ""

        col_widths = [len(h) for h in headers]
        for row in rows:
            for idx, cell in enumerate(row):
                if idx < len(col_widths):
                    col_widths[idx] = max(col_widths[idx], len(str(cell)))
                else:
                    col_widths.append(len(str(cell)))

        def format_row(cells: List[str]) -> str:
            padded = [str(c).ljust(col_widths[i]) for i, c in enumerate(cells)]
            return "| " + " | ".join(padded) + " |"

        separator = "+-" + "-+-".join(["-" * w for w in col_widths]) + "-+"

        lines = [separator, format_row(headers), separator]
        for r in rows:
            lines.append(format_row(r))
        lines.append(separator)
        return "\n".join(lines)
