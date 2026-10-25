"""
OSIRIS Diff Viewer
==================

Generates unified diffs and formats them with syntax coloration for terminal display.
"""

from __future__ import annotations

import difflib
from typing import List, Optional

from osiris_cli.output_renderer import Colors, OutputRenderer  # noqa: F401


class DiffViewer:
    """Generates and renders colored unified diffs."""

    def __init__(self, renderer: Optional[OutputRenderer] = None):
        self.renderer = renderer or OutputRenderer()

    def generate_diff(
        self,
        original_text: str,
        new_text: str,
        from_file: str = "original",
        to_file: str = "proposed"
    ) -> List[str]:
        orig_lines = original_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        return list(difflib.unified_diff(orig_lines, new_lines, fromfile=from_file, tofile=to_file))

    def render_diff(self, diff_lines: List[str]) -> str:
        if not diff_lines:
            return self.renderer.dim("  (No changes)")

        colored_lines = []
        for line in diff_lines:
            if line.startswith("---") or line.startswith("+++"):
                colored_lines.append(self.renderer.bold(line.rstrip()))
            elif line.startswith("@@"):
                colored_lines.append(self.renderer.cyan(line.rstrip()))
            elif line.startswith("+"):
                colored_lines.append(self.renderer.green(line.rstrip()))
            elif line.startswith("-"):
                colored_lines.append(self.renderer.red(line.rstrip()))
            else:
                colored_lines.append(self.renderer.dim(line.rstrip()))

        return "\n".join(colored_lines)
