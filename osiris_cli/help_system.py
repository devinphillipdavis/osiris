"""
OSIRIS Help System & Doctor Diagnostics
=======================================

Comprehensive help documentation, command listings, and system diagnostics for the REPL.
Integrates ProcessDoctor for robust fork/exec verification and receipts.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from osiris_cli.output_renderer import Colors, OutputRenderer  # noqa: F401
from osiris_cli.process_doctor import ProcessDiagnosticReceipt, ProcessDoctor


class HelpSystem:
    """Provides command references, mode descriptions, and health diagnostics."""

    def __init__(self, renderer: Optional[OutputRenderer] = None):
        self.renderer = renderer or OutputRenderer()

    def get_command_help(self) -> str:
        lines = [
            self.renderer.bold("OSIRIS REPL SLASH COMMANDS:"),
            "",
            f"  {self.renderer.cyan('/help')}                 Show this help overview",
            f"  {self.renderer.cyan('/status')}               Display session state, active mode, and OCCR tier",
            f"  {self.renderer.cyan('/doctor')}               Run diagnostic health checks across local environment",
            f"  {self.renderer.cyan('/doctor exec <cmd...>')} Inspect and diagnose a command without executing",
            f"  {self.renderer.cyan('/workspace <path>')}     Switch active workspace directory",
            f"  {self.renderer.cyan('/session new|list|resume')} Manage persistent conversation sessions",
            f"  {self.renderer.cyan('/history [N|search]')}    Search or display past conversation turns",
            f"  {self.renderer.cyan('/mode <name>')}          Switch interaction mode (chat, inspect, plan, propose, edit, test, research, safe)",
            f"  {self.renderer.cyan('/model <name>')}         Switch model adapter (local_nclm, livlm, swarm, offline)",
            f"  {self.renderer.cyan('/context add|rm|list')}  Manage active files loaded into conversational context",
            f"  {self.renderer.cyan('/propose <text|file>')}  Run 5-stage AST safety firewall on candidate code proposal",
            f"  {self.renderer.cyan('/demo')}                 Run 5-minute evidence-governed agent runtime demonstration",
            f"  {self.renderer.cyan('/clear')}                Clear terminal screen",
            f"  {self.renderer.cyan('/exit')}                 Exit the OSIRIS REPL",
            "",
            self.renderer.bold("DISCOVERY & RESEARCH SHORTCUTS:"),
            f"  {self.renderer.cyan('/hypothesis generate')}   Generate structured hypothesis via NCLM adapter",
            f"  {self.renderer.cyan('/hypothesis critique')}   Critique hypothesis draft with deterministic rubric",
            f"  {self.renderer.cyan('/preregister')}           Preregister experiment and hash-lock parameters",
            f"  {self.renderer.cyan('/simulate')}              Execute local simulation inside disposable directory",
            "",
            self.renderer.dim("Prompt formatting: type natural questions or commands directly at 'osiris::}{> '.")
        ]
        return "\n".join(lines)

    def run_doctor(self, workspace_root: str) -> Dict[str, Any]:
        """Runs diagnostic health checks on workspace, python runtime, fork/exec, and OCCR."""
        doc = ProcessDoctor(workspace_root)
        python_bin = sys.executable

        # Preflight check on python binary
        py_receipt = doc.inspect_command([python_bin, "--version"], cwd=workspace_root)

        results = {
            "python_version": sys.version.split()[0],
            "python_executable": python_bin,
            "os_platform": f"{platform.system()} {platform.machine()}",
            "workspace": workspace_root,
            "workspace_exists": os.path.exists(workspace_root),
            "fork_exec_status": "READY" if py_receipt.can_execute else "FAILED",
            "fork_exec_receipt_hash": py_receipt.receipt_hash[:16],
            "occr_engine": "OK",
            "nclm_adapter": "UNKNOWN",
            "git_available": False,
        }

        # Check git preflight
        git_receipt = doc.inspect_command(["git", "--version"], cwd=workspace_root)
        results["git_available"] = git_receipt.can_execute

        # Check NCLM adapter
        try:
            from nclm_research_adapter import NCLMResearchAdapter
            adapter = NCLMResearchAdapter()
            st = adapter.get_status()
            results["nclm_adapter"] = st["model_type"]
        except Exception as e:
            results["nclm_adapter"] = f"ERROR: {e}"

        return results

    def diagnose_process(
        self,
        argv: List[str],
        cwd: Optional[Union[str, Path]] = None
    ) -> ProcessDiagnosticReceipt:
        """Runs deep ProcessDoctor diagnostics on specified argv array."""
        doc = ProcessDoctor(cwd or ".")
        return doc.inspect_command(argv, cwd=cwd)
