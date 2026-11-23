import pytest

from agent.registry import AgentProfile, AgentRegistry
from agent.routing import AgentRouter, AgentUnavailableError
from bridge.context import Context, ContextType


@pytest.fixture
def registry(tmp_path):
    return AgentRegistry(
        [
            AgentProfile("primary", "Primary", str(tmp_path / "primary")),
            AgentProfile("research", "Research", str(tmp_path / "research")),
            AgentProfile(
                "disabled", "Disabled", str(tmp_path / "disabled"), enabled=False
            ),
        ],
        default_agent_id="primary",
    )


def _router(registry):
    return AgentRouter(registry)


def test_explicit_selection_is_honored(registry):
    assert _router(registry).resolve(explicit_agent_id="research") == "research"


def test_no_selection_uses_configured_default(registry):
    assert _router(registry).resolve() == "primary"


def test_explicit_selection_of_unavailable_agent_refuses(registry):
    with pytest.raises(AgentUnavailableError, match="missing or disabled"):
        _router(registry).resolve(explicit_agent_id="disabled")


def test_channel_instance_binding_routes_to_bound_agent(registry):
    """The channel instance that delivered the message owns the route: its
    bound_agent_id decides which Agent answers."""
    router = _router(registry)
    context = Context(ContextType.TEXT, "hi", kwargs={})
    context["channel_type"] = "feishu"
    context["bound_agent_id"] = "research"

    assert router.resolve_context(context) == "research"
    assert context["agent_id"] == "research"


def test_explicit_agent_id_overrides_instance_binding(registry):
    """A per-message agent_id (e.g. a console request) wins over the instance
    binding."""
    router = _router(registry)
    context = Context(ContextType.TEXT, "hi", kwargs={})
    context["bound_agent_id"] = "research"
    context["agent_id"] = "primary"

    assert router.resolve_context(context) == "primary"


def test_instance_binding_falls_back_to_default_when_unavailable(registry):
    """If the instance's bound Agent is disabled/missing, routing falls back to
    the default Agent rather than dropping the message."""
    router = _router(registry)
    context = Context(ContextType.TEXT, "hi", kwargs={})
    context["channel_type"] = "feishu"
    context["bound_agent_id"] = "disabled"

    assert router.resolve_context(context) == "primary"


def test_context_without_binding_uses_default(registry):
    """No bound_agent_id and no explicit selection -> the default Agent."""
    router = _router(registry)
    context = Context(ContextType.TEXT, "hi", kwargs={})
    context["channel_type"] = "feishu"

    assert router.resolve_context(context) == "primary"
    assert context["agent_id"] == "primary"
