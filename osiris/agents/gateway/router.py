"""Deterministic model and adapter router."""

from __future__ import annotations

from .contracts import AgentAdapter, AuthorizedAgentRequest


class RoutingError(Exception):
    pass


class ModelRouter:
    """Routes requests based on data classification and budget."""

    def __init__(self, adapters: dict[str, AgentAdapter]):
        self._adapters = adapters

    def route(self, request: AuthorizedAgentRequest) -> AgentAdapter:
        # Strict isolation: RESTRICTED data or offline task classes must route to replay
        if request.data_classification in ("RESTRICTED", "INTERNAL_CONFIDENTIAL"):
            if "replay" not in self._adapters:
                raise RoutingError("No offline replay adapter available for RESTRICTED request")
            return self._adapters["replay"]

        # Route standard requests to Antigravity if available
        if "antigravity" in self._adapters:
            return self._adapters["antigravity"]

        if "replay" in self._adapters:
            return self._adapters["replay"]

        raise RoutingError("No suitable adapter found for request")
