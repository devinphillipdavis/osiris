"""Antigravity SDK Adapter."""

from __future__ import annotations

import asyncio

try:
    from google_antigravity import LocalAgentConfig
except ImportError:  # optional extra — adapter stays importable without it
    LocalAgentConfig = None

from ..contracts import (
    AgentAdapter,
    AgentResult,
    AuthorizedAgentRequest,
)
from osiris.substrate import execution_timeout_s


class AntigravityAdapter(AgentAdapter):
    """Adapter bridging OSIRIS AuthorizedAgentRequest to Google Antigravity Agents."""

    @staticmethod
    def is_available() -> bool:
        """True when the optional google_antigravity SDK is importable."""
        return LocalAgentConfig is not None

    def capabilities(self) -> frozenset[str]:
        # Based on OSIRIS governance, Antigravity inherits baseline capabilities
        return frozenset({"READ_ONLY_ANALYSIS", "RETURN_STRUCTURED_PROPOSAL"})

    def _error(self, request: AuthorizedAgentRequest, message: str) -> AgentResult:
        return AgentResult(
            request_id=request.request_id,
            status="ERROR",
            provider="google_antigravity",
            proposals=(),
            usage={"tokens": 0, "cost_usd": 0.0},
            error=message,
        )

    async def run(self, request: AuthorizedAgentRequest) -> AgentResult:
        if not self.is_available():
            return self._error(
                request,
                "google_antigravity is not installed; "
                "install the optional extra to enable AntigravityAdapter",
            )

        # Node Alpha caps delegated work at 300 s, Node Beta at 1800 s.
        timeout = execution_timeout_s()
        try:
            # 1. Initialize Antigravity Local Agent bound to the session constraint
            agent = LocalAgentConfig(
                name="osiris_antigravity_delegate",
                description="Delegated executor for OSIRIS tasks",
            ).build()

            # 2. Execute task using the antigravity runner, inside the substrate horizon
            response = await asyncio.wait_for(
                agent.execute_task(request.task), timeout=timeout
            )

            # 3. Map back to OSIRIS AgentResult
            return AgentResult(
                request_id=request.request_id,
                status="SUCCESS",
                provider="google_antigravity",
                proposals=(),  # TODO: Map Antigravity tool proposals to ActionProposal
                usage={"tokens": getattr(response, "total_tokens", 0), "cost_usd": 0.0},
                error=None,
            )
        except asyncio.TimeoutError:
            return self._error(
                request, f"antigravity task exceeded substrate horizon of {timeout:.1f}s"
            )
        except Exception as e:
            return self._error(request, str(e))
