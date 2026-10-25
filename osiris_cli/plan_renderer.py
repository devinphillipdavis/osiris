"""
OSIRIS Plan Renderer
====================

Renders structured execution plans with goal, file impacts, verification, and risk.
"""

from __future__ import annotations

from dataclasses import dataclass, field  # noqa: F401
from typing import List, Optional

from osiris_cli.output_renderer import Colors, OutputRenderer  # noqa: F401


@dataclass
class PlanStep:
    step_number: int
    action: str
    target_file: str
    rationale: str
    status: str = "PENDING"  # PENDING, IN_PROGRESS, COMPLETED, FAILED


@dataclass
class ExecutionPlan:
    goal: str
    impacted_files: List[str]
    steps: List[PlanStep]
    verification_command: str
    rollback_strategy: str
    risk_level: str  # LOW, MEDIUM, HIGH


class PlanRenderer:
    """Formats structured execution plans for terminal display."""

    def __init__(self, renderer: Optional[OutputRenderer] = None):
        self.renderer = renderer or OutputRenderer()

    def render(self, plan: ExecutionPlan) -> str:
        lines = []
        lines.append(self.renderer.bold(f"📋 EXECUTION PLAN: {plan.goal}"))
        lines.append(f"  {self.renderer.dim('Risk Level:')} {self._format_risk(plan.risk_level)}")
        lines.append(f"  {self.renderer.dim('Impacted Files:')} {', '.join(plan.impacted_files) if plan.impacted_files else 'None'}")
        lines.append("")
        lines.append(self.renderer.bold("  Steps:"))

        for s in plan.steps:
            status_badge = f"[{s.status}]"
            step_line = f"    {s.step_number}. {status_badge} {self.renderer.cyan(s.action)} -> {s.target_file}"
            lines.append(step_line)
            if s.rationale:
                lines.append(f"       {self.renderer.dim('Rationale: ' + s.rationale)}")

        lines.append("")
        lines.append(f"  {self.renderer.bold('Verification:')} `{plan.verification_command}`")
        lines.append(f"  {self.renderer.bold('Rollback:')} {plan.rollback_strategy}")
        return "\n".join(lines)

    def _format_risk(self, risk: str) -> str:
        r = risk.upper()
        if r == "LOW":
            return self.renderer.green(r)
        elif r == "MEDIUM":
            return self.renderer.yellow(r)
        else:
            return self.renderer.red(r)
