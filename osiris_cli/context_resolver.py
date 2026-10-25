"""
OSIRIS Context Resolver
=======================

Resolves file references (@file), symbols (#symbol), line ranges, and active context.
"""

from __future__ import annotations

import os  # noqa: F401
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple  # noqa: F401


class ContextResolver:
    """Manages files and symbols actively loaded in conversational context."""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.active_files: Set[str] = set()

    def add_file(self, file_path_str: str) -> Tuple[bool, str]:
        """Add a file to the active context after verifying existence and safety."""
        clean_path = file_path_str.lstrip("@").strip()
        target = (self.workspace_root / clean_path).resolve()

        # Guard against path traversal outside root
        try:
            target.relative_to(self.workspace_root)
        except ValueError:
            return False, f"Path traversal blocked: '{clean_path}' is outside workspace root."

        if not target.exists():
            return False, f"File does not exist: '{clean_path}'"
        if not target.is_file():
            return False, f"Path is not a regular file: '{clean_path}'"

        rel_path = str(target.relative_to(self.workspace_root))
        self.active_files.add(rel_path)
        return True, f"Added '@{rel_path}' to active context."

    def remove_file(self, file_path_str: str) -> Tuple[bool, str]:
        clean_path = file_path_str.lstrip("@").strip()
        if clean_path in self.active_files:
            self.active_files.remove(clean_path)
            return True, f"Removed '@{clean_path}' from active context."
        return False, f"File '@{clean_path}' was not in active context."

    def clear(self) -> None:
        self.active_files.clear()

    def list_files(self) -> List[str]:
        return sorted(list(self.active_files))

    def extract_mentions(self, text: str) -> Dict[str, List[str]]:
        """Extract @file and #symbol references from user prompt text."""
        files = re.findall(r"@([a-zA-Z0-9_\-./]+)", text)
        symbols = re.findall(r"#([a-zA-Z0-9_]+)", text)
        return {
            "files": files,
            "symbols": symbols
        }

    def read_context_contents(self, max_bytes_per_file: int = 50000) -> Dict[str, str]:
        """Read content of all active context files, truncating if necessary."""
        contents: Dict[str, str] = {}
        for rel_path in self.list_files():
            full_path = self.workspace_root / rel_path
            if full_path.exists() and full_path.is_file():
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        data = f.read(max_bytes_per_file)
                        contents[rel_path] = data
                except Exception as e:
                    contents[rel_path] = f"[Error reading file: {e}]"
        return contents
