"""Offline deterministic ReplayAdapter."""

from __future__ import annotations

import hashlib  # noqa: F401
from typing import Mapping  # noqa: F401

from ..contracts import (
    ActionProposal,  # noqa: F401
    AgentAdapter,  # noqa: F401
    AgentResult,
    AuthorizedAgentRequest,
    compute_sha256,
)


class ReplayAdapter:
    """Deterministic replay adapter with zero network, secret, or subprocess calls."""

    def __init__(self) -> None:
        self._fixtures: dict[str, AgentResult] = {}

    def capabilities(self) -> frozenset[str]:
        return frozenset({"READ_ONLY_ANALYSIS", "RETURN_STRUCTURED_PROPOSAL", "REPLAY_FIXTURE"})

    def register_fixture(self, key: str, result: AgentResult) -> None:
        self._fixtures[key] = result

    def compute_request_key(self, request: AuthorizedAgentRequest) -> str:
        payload = f"{request.task}:{request.data_classification}:{request.authority_scope}"
        return compute_sha256(payload)

    async def run(self, request: AuthorizedAgentRequest) -> AgentResult:
        key = self.compute_request_key(request)
        if key not in self._fixtures:
            # Fallback to direct task string
            key = request.task

        if key not in self._fixtures:
            return AgentResult(
                request_id=request.request_id,
                status="NOT_FOUND",
                provider="replay",
                proposals=(),
                usage={"tokens": 0, "cost_usd": 0.0},
                error=f"No matching replay fixture found for key: {key}",
            )

        fixture = self._fixtures[key]
        return AgentResult(
            request_id=request.request_id,
            status=fixture.status,
            provider="replay",
            proposals=fixture.proposals,
            usage=fixture.usage,
            error=fixture.error,
        )
