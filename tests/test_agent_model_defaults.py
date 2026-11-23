"""Which model answers: the conversation's choice, the Agent's, or the global one."""

import pytest

from bridge.agent_bridge import AgentLLMModel


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setattr(
        "bridge.agent_bridge.conf", lambda: {"model": "global-model"}, raising=False
    )
    return AgentLLMModel.__new__(AgentLLMModel)


class TestWhichModelAnswers:
    def test_the_global_one_when_nothing_else_is_set(self, model):
        assert model.model == "global-model"

    def test_the_agents_own_beats_the_global_one(self, model):
        model.set_agent_default(None, "agent-model")
        assert model.model == "agent-model"

    def test_the_conversations_choice_beats_the_agents_own(self, model):
        model.set_agent_default(None, "agent-model")
        model.set_session_override(None, "pinned-model")
        assert model.model == "pinned-model"

    def test_clearing_the_conversation_falls_back_to_the_agent(self, model):
        """What an invited teammate gets: the host's pin is dropped, and it
        answers on the model it was configured with, not the global one."""
        model.set_agent_default(None, "agent-model")
        model.set_session_override(None, "pinned-model")
        model.set_session_override(None, None)
        assert model.model == "agent-model"

    def test_a_blank_default_is_the_same_as_none(self, model):
        model.set_agent_default("  ", "  ")
        assert model.model == "global-model"


class TestRouting:
    """A model without its provider asks the wrong vendor for it."""

    def test_the_agents_provider_routes_its_model(self, model):
        model.set_agent_default("claude", "some-model")
        assert model._resolve_bot_type("some-model") == "claude"

    def test_the_conversations_provider_still_wins(self, model):
        model.set_agent_default("claude", "some-model")
        model.set_session_override("deepseek", "other-model")
        assert model._resolve_bot_type("other-model") == "deepseek"


class TestRebuildingTheBot:
    def test_changing_the_default_drops_the_cached_bot(self, model):
        model._bot = object()
        model.set_agent_default(None, "agent-model")
        assert model._bot is None

    def test_setting_the_same_default_leaves_it_alone(self, model):
        model.set_agent_default(None, "agent-model")
        cached = object()
        model._bot = cached
        model.set_agent_default(None, "agent-model")
        assert model._bot is cached
