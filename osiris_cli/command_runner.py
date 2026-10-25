"""
OSIRIS Safe Command Runner
==========================

Local subprocess execution engine integrated with ProcessDoctor preflight diagnostics.
Guarantees zero shell=True, strict argument arrays, timeout enforcement, and verifiable execution receipts.
"""

from __future__ import annotations

import os  # noqa: F401
import shlex
import sys  # noqa: F401
import time  # noqa: F401
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union  # noqa: F401

from osiris.substrate import interactive_timeout_s
from osiris_cli.process_doctor import ProcessDiagnosticReceipt, ProcessDoctor


class CommandRunner:
    """Safely runs local shell commands without invoking shell=True."""

    ALLOWED_PREFIXES = [
        "python", "python3", "pytest", "git", "ls", "grep", "cat", "find",
        "mkdir", "cp", "echo", "pwd", "tree", "node", "which", "head", "tail"
    ]

    def __init__(
        self,
        workspace_root: Union[str, Path],
        timeout_seconds: Optional[float] = None,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        # Interactive horizon, not the batch horizon: a stuck child must not hold
        # the REPL for 1800 s on Node Beta.
        self.timeout_seconds = (
            interactive_timeout_s() if timeout_seconds is None else timeout_seconds
        )
        self.doctor = ProcessDoctor(self.workspace_root)
        self.last_receipt: Optional[ProcessDiagnosticReceipt] = None

    def is_command_allowed(self, cmd_args: List[str]) -> Tuple[bool, str]:
        if not cmd_args:
            return False, "Empty command."

        binary = Path(cmd_args[0]).name
        if binary not in self.ALLOWED_PREFIXES and cmd_args[0] not in self.ALLOWED_PREFIXES:
            return False, f"Command '{cmd_args[0]}' is not in allowed prefix list."

        # Disallow chained operators inside arguments
        disallowed = [";", "&&", "||", "|", "`", "$("]
        for arg in cmd_args:
            for op in disallowed:
                if op in arg:
                    return False, f"Chained shell operator '{op}' is forbidden."

        return True, "Command allowed."

    def run(
        self,
        cmd_str_or_args: List[str] | str,
        cwd: Optional[Union[str, Path]] = None,
        timeout: Optional[int] = None
    ) -> Tuple[int, str, str]:
        """
        Runs command with timeout. Returns (exit_code, stdout, stderr).
        Never uses shell=True.
        """
        code, stdout, stderr, receipt = self.run_with_receipt(
            cmd_str_or_args, cwd=cwd, timeout=timeout
        )
        self.last_receipt = receipt
        return code, stdout, stderr

    def run_with_receipt(
        self,
        cmd_str_or_args: List[str] | str,
        cwd: Optional[Union[str, Path]] = None,
        timeout: Optional[int] = None
    ) -> Tuple[int, str, str, ProcessDiagnosticReceipt]:
        """
        Executes command through ProcessDoctor with preflight verification and receipt generation.
        """
        if isinstance(cmd_str_or_args, str):
            cmd_args = shlex.split(cmd_str_or_args)
        else:
            cmd_args = list(cmd_str_or_args)

        allowed, reason = self.is_command_allowed(cmd_args)
        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        t_out = timeout or self.timeout_seconds

        if not allowed:
            # Emit fail-closed receipt for policy violation
            receipt = self.doctor.inspect_command(cmd_args, cwd=work_dir)
            return -1, "", f"BLOCKED BY POLICY: {reason}", receipt

        # Process through ProcessDoctor
        exit_code, stdout, stderr, receipt = self.doctor.execute_with_receipt(
            argv=cmd_args,
            cwd=work_dir,
            timeout=t_out
        )
        self.last_receipt = receipt
        return exit_code, stdout, stderr, receipt
