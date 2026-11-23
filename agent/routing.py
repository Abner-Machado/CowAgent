"""Deterministic inbound routing for agent workspaces.

Routing is driven entirely by channel instances: each running channel carries
the id of the Agent it is bound to (``bound_agent_id`` in the message context,
sourced from ``channel_instances[].agent_id``). There is no separate binding
table — the instance that received a message decides which Agent answers it,
and an explicit per-message ``agent_id`` (e.g. a console request) overrides it.
Anything unrouted falls back to the default Agent.
"""

from __future__ import annotations

import threading
from typing import Mapping, Optional

from common.log import logger

from agent.registry import AgentRegistry


class AgentUnavailableError(RuntimeError):
    """Raised when a route resolves to a missing or disabled agent."""


class AgentRouter:
    """Resolve explicit selections and channel-instance bindings to agents."""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    @classmethod
    def from_config(cls, settings: Mapping, registry: AgentRegistry) -> "AgentRouter":
        # Kept for call sites that build a router from settings; routing no
        # longer reads anything out of settings beyond the registry itself.
        return cls(registry)

    def _require_enabled(self, agent_id: Optional[str], source: str) -> str:
        """A route that names an unavailable agent is a configuration error.

        Serving it with the default agent instead would answer the user with a
        different persona, memory and workspace than the one they are bound to,
        and nothing in the conversation would reveal the substitution.
        """
        try:
            return self.registry.get_addressed(agent_id).id
        except Exception as exc:
            raise AgentUnavailableError(
                f"{source} selected agent {agent_id!r}, which is missing or disabled"
            ) from exc

    def resolve(self, explicit_agent_id: str = None) -> str:
        """An explicit agent id if given and enabled, else the default agent."""
        if explicit_agent_id:
            return self._require_enabled(explicit_agent_id, "explicit route")
        return self.registry.default_agent_id

    def resolve_context(self, context) -> str:
        if context is None:
            return self.registry.default_agent_id
        # The channel instance that delivered this message owns the route: it
        # carries its own credentials and identity, so its binding decides which
        # Agent answers. An explicit per-message agent_id (console requests)
        # wins over it; anything else falls back to the default Agent.
        bound_agent_id = context.get("bound_agent_id")
        explicit = context.get("agent_id")
        if bound_agent_id and not explicit:
            try:
                agent_id = self._require_enabled(bound_agent_id, "channel instance binding")
                context["agent_id"] = agent_id
                return agent_id
            except AgentUnavailableError:
                logger.warning(
                    f"[Routing] channel instance bound Agent "
                    f"{bound_agent_id!r} unavailable; falling back to default"
                )
        agent_id = self.resolve(explicit_agent_id=explicit)
        context["agent_id"] = agent_id
        return agent_id


_router_instance: Optional[AgentRouter] = None
_router_signature: Optional[tuple] = None
_router_pinned: bool = False
_router_lock = threading.Lock()


def get_agent_router(registry: AgentRegistry = None) -> AgentRouter:
    """Router for the current registry.

    Rebuilt when the registry identity changes (e.g. the console reloads the
    roster at runtime) rather than cached forever on first access.
    """

    global _router_instance, _router_signature
    from agent.registry import get_agent_registry

    active_registry = registry or get_agent_registry()
    signature = (id(active_registry),)
    with _router_lock:
        if _router_pinned and _router_instance is not None:
            return _router_instance
        if _router_instance is None or _router_signature != signature:
            _router_instance = AgentRouter(active_registry)
            _router_signature = signature
        return _router_instance


def set_agent_router(router: Optional[AgentRouter]) -> None:
    """Pin a router, or pass None to go back to following the registry."""

    global _router_instance, _router_signature, _router_pinned
    with _router_lock:
        _router_instance = router
        _router_signature = None
        _router_pinned = router is not None
