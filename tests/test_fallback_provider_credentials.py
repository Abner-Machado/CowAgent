# encoding:utf-8
"""A chat fallback on a custom provider must switch credentials, not just model.

Regression coverage for the bug where the fallback changed the model id but
kept the primary provider's api_base/api_key: ``ChatGPTBot`` resolved its
credentials from the globally configured ``bot_type`` instead of the
``custom:<id>`` the run had been routed to, so the fallback's model was sent
to the primary vendor's endpoint — which answers 404 "model is not found".

``AgentLLMModel._resolve_bot_type`` already resolved the right provider; the
bot simply ignored it. These tests pin the whole chain.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config as config_module
from config import Config


def set_conf(d):
    """Install a fresh Config as the global config used by conf()."""
    config_module.config = Config(d)


PROVIDERS = [
    {"id": "primary1", "name": "primary", "api_key": "key-primary",
     "api_base": "https://primary.example.com/v1", "model": "primary-model"},
    {"id": "backup22", "name": "backup", "api_key": "key-backup",
     "api_base": "https://backup.example.com/v1", "model": "backup-model"},
]

# The upstream (single-model) fallback shape.
FALLBACK = {"enabled": True, "provider": "custom:backup22",
            "model": "backup-model", "max_switches": 1}


@pytest.fixture
def custom_primary():
    """Global routing configured for the primary custom provider."""
    set_conf({
        "bot_type": "custom:primary1",
        "model": "primary-model",
        "custom_providers": [dict(p) for p in PROVIDERS],
    })


class TestCreateBotCredentialRouting:
    """create_bot() lets a caller choose which provider's creds it uses."""

    def test_explicit_credential_type_wins_over_the_global_one(self, custom_primary):
        from models.bot_factory import create_bot

        bot = create_bot("custom:backup22", credential_bot_type="custom:backup22")
        assert bot._api_base == "https://backup.example.com/v1"
        assert bot._api_key == "key-backup"

    def test_omitting_the_argument_keeps_reading_the_global_provider(self, custom_primary):
        """Every pre-existing one-argument caller is unaffected."""
        from models.bot_factory import create_bot

        bot = create_bot("custom:primary1")
        assert bot._api_base == "https://primary.example.com/v1"
        assert bot._api_key == "key-primary"

    def test_a_non_custom_global_provider_is_unchanged(self):
        set_conf({
            "bot_type": "chatGPT",
            "open_ai_api_key": "sk-openai",
            "open_ai_api_base": "https://api.openai.com/v1",
        })
        from models.bot_factory import create_bot

        bot = create_bot("chatGPT")
        assert bot._api_base == "https://api.openai.com/v1"
        assert bot._api_key == "sk-openai"


def _engaged_model(monkeypatch):
    """An AgentLLMModel sitting on its fallback link (stubbed config)."""
    conf = {"model": "primary-model", "chat_fallback": dict(FALLBACK)}
    monkeypatch.setattr("bridge.agent_bridge.conf", lambda: conf, raising=False)
    from bridge.agent_bridge import AgentLLMModel

    model = AgentLLMModel.__new__(AgentLLMModel)
    assert model.use_fallback() is True
    return model


class TestFallbackRouting:
    """The bridge passes the fallback's provider all the way to the bot."""

    def test_the_resolved_type_is_the_fallbacks_provider(self, monkeypatch):
        model = _engaged_model(monkeypatch)
        assert model.model == "backup-model"
        assert model._resolve_bot_type(model.model) == "custom:backup22"

    def test_the_bot_is_built_with_the_fallbacks_provider(self, monkeypatch):
        """The credential provider handed to create_bot must be the link's."""
        model = _engaged_model(monkeypatch)
        seen = {}

        class FakeBot:
            # Present so add_openai_compatible_support() leaves it alone.
            def call_with_tools(self, *a, **kw):
                raise NotImplementedError

        def fake_create_bot(bot_type, credential_bot_type=None):
            seen["bot_type"] = bot_type
            seen["credential_bot_type"] = credential_bot_type
            return FakeBot()

        monkeypatch.setattr("models.bot_factory.create_bot", fake_create_bot)
        model.bot  # triggers the lazy build

        assert seen["bot_type"] == "custom:backup22"
        assert seen["credential_bot_type"] == "custom:backup22"

    def test_credentials_resolve_to_the_fallback_endpoint(self, custom_primary):
        """Given the link's provider, the bot reads the link's credentials."""
        from models.custom_provider import resolve_custom_credentials

        assert resolve_custom_credentials("custom:backup22") == (
            "key-backup", "https://backup.example.com/v1", "backup-model")

    def test_the_primary_route_still_reads_the_global_provider(self, custom_primary):
        """No engaged fallback -> the historical call shape is untouched."""
        from models.custom_provider import resolve_custom_credentials

        assert resolve_custom_credentials() == (
            "key-primary", "https://primary.example.com/v1", "primary-model")
