"""Central AgentGateway coordinating routing, execution, and capability governance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping  # noqa: F401

from .contracts import (
    ActionProposal,  # noqa: F401
    AgentResult,
    AuthorizedAgentRequest,
    ExecutionGrant,
)
from .governor import CapabilityGovernor
from .router import ModelRouter


@dataclass(frozen=True)
class GatewayResponse:
    request_id: str
    result: AgentResult
    grants: tuple[ExecutionGrant, ...]


class AgentGateway:
    """Authoritative gateway entry point."""

    def __init__(self, router: ModelRouter, governor: CapabilityGovernor):
        self._router = router
        self._governor = governor

    async def process(self, request: AuthorizedAgentRequest) -> GatewayResponse:
        adapter = self._router.route(request)
        result = await adapter.run(request)

        grants: list[ExecutionGrant] = []
        for proposal in result.proposals:
            grant = self._governor.evaluate(proposal, request)
            grants.append(grant)

        return GatewayResponse(
            request_id=request.request_id,
            result=result,
            grants=tuple(grants),
        )
