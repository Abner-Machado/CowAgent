"""The pre-chain ``chat_fallback`` must survive an upgrade.

``chat_fallback`` used to hold a single backup: ``{enabled, provider, model,
max_switches}``. It now holds an ordered chain. A user who had already
configured a backup model — and who is exactly the person relying on the
fallback — would otherwise load into an empty chain and silently lose their
safety net on the first launch after upgrading.

``max_switches`` is intentionally not carried over: the chain length is the new
bound, and the old counter never bounded anything, since the fallback was
already sticky for a whole run.
"""

from config import _migrate_chat_fallback


class TestMigratingTheLegacyShape:
    def test_a_legacy_backup_becomes_a_one_link_chain(self):
        cfg = {"chat_fallback": {
            "enabled": True,
            "provider": "openai",
            "model": "backup-model",
            "max_switches": 3,
        }}
        _migrate_chat_fallback(cfg)
        assert cfg["chat_fallback"] == {
            "enabled": True,
            "chain": [{"provider": "openai", "model": "backup-model"}],
        }

    def test_a_half_configured_legacy_entry_yields_an_empty_chain(self):
        """No provider or no model means there was never a usable backup; an
        empty chain keeps the fallback off rather than inventing one."""
        cfg = {"chat_fallback": {"enabled": True, "provider": "openai", "model": ""}}
        _migrate_chat_fallback(cfg)
        assert cfg["chat_fallback"]["chain"] == []

    def test_a_disabled_legacy_entry_stays_disabled(self):
        cfg = {"chat_fallback": {
            "enabled": False, "provider": "openai", "model": "backup-model",
        }}
        _migrate_chat_fallback(cfg)
        assert cfg["chat_fallback"]["enabled"] is False
        assert cfg["chat_fallback"]["chain"] == [
            {"provider": "openai", "model": "backup-model"}
        ]

    def test_the_new_shape_is_left_alone(self):
        """Idempotent: re-running must not wrap an existing chain in another."""
        cfg = {"chat_fallback": {
            "enabled": True,
            "chain": [{"provider": "openai", "model": "backup-1"},
                      {"provider": "qianfan", "model": "backup-2"}],
        }}
        _migrate_chat_fallback(cfg)
        assert cfg["chat_fallback"]["chain"] == [
            {"provider": "openai", "model": "backup-1"},
            {"provider": "qianfan", "model": "backup-2"},
        ]

    def test_a_stale_max_switches_is_dropped_from_the_new_shape(self):
        cfg = {"chat_fallback": {
            "enabled": True,
            "chain": [{"provider": "openai", "model": "backup-1"}],
            "max_switches": 5,
        }}
        _migrate_chat_fallback(cfg)
        assert "max_switches" not in cfg["chat_fallback"]
        assert cfg["chat_fallback"]["chain"] == [
            {"provider": "openai", "model": "backup-1"}
        ]

    def test_a_missing_entry_is_tolerated(self):
        cfg = {}
        _migrate_chat_fallback(cfg)
        assert "chat_fallback" not in cfg

    def test_a_non_dict_entry_is_tolerated(self):
        cfg = {"chat_fallback": "openai/backup-model"}
        _migrate_chat_fallback(cfg)
        assert cfg["chat_fallback"] == "openai/backup-model"
