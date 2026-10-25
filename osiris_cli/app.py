"""
OSIRIS CLI Application Entry Point
==================================

Usage:
  osiris [--workspace <path>] [--session <id>] [--mode <mode>] [--model <model>]
  osiris -c "<command or prompt>"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path  # noqa: F401

from osiris_cli.repl import OsirisREPL
from osiris_cli.session_manager import SessionManager  # noqa: F401


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="osiris",
        description="OSIRIS Conversational Terminal REPL & Evidence-Governed Engineering Copilot"
    )
    parser.add_argument("-w", "--workspace", default=".", help="Target workspace path")
    parser.add_argument("-s", "--session", help="Session ID to resume or create")
    parser.add_argument("-m", "--mode", default="inspect", help="Initial interaction mode")
    parser.add_argument("--model", default="local_nclm", help="Active model adapter")
    parser.add_argument("-c", "--command", help="Execute single prompt or slash command and exit")

    args = parser.parse_args()

    repl = OsirisREPL(
        workspace_root=args.workspace,
        session_id=args.session,
        mode=args.mode,
        model=args.model
    )

    if args.command:
        # Run one-off command
        response = repl.router.route_turn(args.command)
        if response:
            print(response)
        return 0

    return repl.run()


if __name__ == "__main__":
    sys.exit(main())
