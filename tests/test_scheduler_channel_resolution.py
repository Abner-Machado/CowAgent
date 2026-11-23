"""Regression tests for scheduler channel resolution / readiness (issue #3120).

A weixin bot that runs as a channel_instance registers under its instance_id
(e.g. ``weixin-c696...``). A scheduled task whose action never stored an
instance_id must still resolve to that live instance instead of a bare,
never-started ``create_channel`` singleton, otherwise its token map is empty and
readiness defers the task forever.
"""

import sys
import types

import agent.tools.scheduler.integration as integration


class _FakeChannel:
    def __init__(self, channel_type, instance_id="", tokens=None):
        self.channel_type = channel_type
        self.instance_id = instance_id
        self._context_tokens = dict(tokens or {})


class _FakeManager:
    def __init__(self, channels):
        # channels: dict registry_name -> _FakeChannel
        self._channels = dict(channels)

    def get_channel(self, name):
        return self._channels.get(name)

    def find_channels_by_type(self, channel_type):
        return [
            (name, ch)
            for name, ch in self._channels.items()
            if getattr(ch, "channel_type", "") == channel_type
        ]


def _install_manager(monkeypatch, manager):
    """Make ``common.channel_registry.get_channel_manager`` return our fake."""
    import common.channel_registry as registry

    monkeypatch.setattr(registry, "get_channel_manager", lambda: manager)


class _FakeRecipientStore:
    def __init__(self, entries):
        self._entries = list(entries)

    def list(self):
        return list(self._entries)


def _install_directory(monkeypatch, entries):
    monkeypatch.setattr(
        integration,
        "_get_shared_recipient_store",
        lambda: _FakeRecipientStore(entries),
    )


def test_resolves_live_instance_when_task_has_no_instance_id(monkeypatch):
    live = _FakeChannel("weixin", "weixin-c6961093a5", tokens={"user@im": "tok"})
    _install_manager(monkeypatch, _FakeManager({"weixin-c6961093a5": live}))
    _install_directory(monkeypatch, [])

    resolved = integration._resolve_delivery_channel("weixin", "", "user@im")

    assert resolved is live


def test_ready_true_for_instance_run_weixin_without_instance_id(monkeypatch):
    live = _FakeChannel("weixin", "weixin-c6961093a5", tokens={"user@im": "tok"})
    _install_manager(monkeypatch, _FakeManager({"weixin-c6961093a5": live}))
    _install_directory(monkeypatch, [])

    assert integration._is_channel_ready("weixin", "user@im", instance_id="") is True


def test_multiple_instances_prefers_the_one_holding_the_receiver(monkeypatch):
    other = _FakeChannel("weixin", "weixin-aaaa", tokens={"someone-else": "t"})
    mine = _FakeChannel("weixin", "weixin-bbbb", tokens={"user@im": "tok"})
    _install_manager(
        monkeypatch,
        _FakeManager({"weixin-aaaa": other, "weixin-bbbb": mine}),
    )
    _install_directory(monkeypatch, [])  # no directory hit -> fall to token match

    resolved = integration._resolve_delivery_channel("weixin", "", "user@im")

    assert resolved is mine


def test_feishu_recovers_correct_instance_from_recipient_directory(monkeypatch):
    """Two Feishu apps; a task with no instance_id must resolve to the app that
    actually owns the open_id, not the first one (which raises open_id cross
    app). The recipient directory is the authoritative source of that mapping."""
    app_a = _FakeChannel("feishu", "feishu-72734a6dbe")
    app_b = _FakeChannel("feishu", "feishu-ec75a1f1f8")
    _install_manager(
        monkeypatch,
        _FakeManager({"feishu-72734a6dbe": app_a, "feishu-ec75a1f1f8": app_b}),
    )
    _install_directory(
        monkeypatch,
        [
            {
                "channel_type": "feishu",
                "instance_id": "feishu-ec75a1f1f8",
                "receiver": "ou_a2a4af",
            }
        ],
    )

    resolved = integration._resolve_delivery_channel("feishu", "", "ou_a2a4af")

    assert resolved is app_b


def test_feishu_refuses_to_guess_between_instances_without_a_directory_hit(monkeypatch):
    """No instance_id and the receiver is unknown to the directory: we must not
    blindly deliver through the first app (that is the cross-app bug). Falling
    through to create_channel is fine — the point is we don't return app_a."""
    app_a = _FakeChannel("feishu", "feishu-72734a6dbe")
    app_b = _FakeChannel("feishu", "feishu-ec75a1f1f8")
    _install_manager(
        monkeypatch,
        _FakeManager({"feishu-72734a6dbe": app_a, "feishu-ec75a1f1f8": app_b}),
    )
    _install_directory(monkeypatch, [])

    bare = object()
    fake_factory = types.ModuleType("channel.channel_factory")
    fake_factory.create_channel = lambda *a, **k: bare
    monkeypatch.setitem(sys.modules, "channel.channel_factory", fake_factory)

    resolved = integration._resolve_delivery_channel("feishu", "", "ou_unknown")

    assert resolved is not app_a
    assert resolved is not app_b
    assert resolved is bare


def test_single_feishu_instance_is_used_directly(monkeypatch):
    """Solo Feishu install: exactly one instance, so it is safe to auto-pick
    even without a directory entry (legacy behaviour preserved)."""
    only = _FakeChannel("feishu", "feishu-72734a6dbe")
    _install_manager(monkeypatch, _FakeManager({"feishu-72734a6dbe": only}))
    _install_directory(monkeypatch, [])

    resolved = integration._resolve_delivery_channel("feishu", "", "ou_a2a4af")

    assert resolved is only


def test_manager_is_shared_across_app_main_duplication(monkeypatch):
    """app.py runs as __main__; a later ``import app`` builds a second module.
    The manager must be held in the shared registry so the scheduler (which
    imports it, not __main__) sees the same object the entry module set — the
    core of issue #3120."""
    import common.channel_registry as registry

    sentinel = object()
    monkeypatch.setattr(registry, "_channel_manager", None)
    try:
        # Whatever the entry module set...
        registry.set_channel_manager(sentinel)
        # ...the scheduler-side import must observe.
        assert registry.get_channel_manager() is sentinel
    finally:
        registry.set_channel_manager(None)


def test_exact_instance_id_still_wins(monkeypatch):
    a = _FakeChannel("weixin", "weixin-aaaa", tokens={"user@im": "t"})
    b = _FakeChannel("weixin", "weixin-bbbb", tokens={"user@im": "t"})
    _install_manager(monkeypatch, _FakeManager({"weixin-aaaa": a, "weixin-bbbb": b}))

    resolved = integration._resolve_delivery_channel("weixin", "weixin-bbbb", "user@im")

    assert resolved is b


def test_bare_singleton_fallback_does_not_hard_block_readiness(monkeypatch):
    """No live instance of the type: the token check is inconclusive, so the
    scheduler must allow the send attempt instead of deferring forever."""
    _install_manager(monkeypatch, _FakeManager({}))

    bare = _FakeChannel("weixin", "", tokens={})
    monkeypatch.setattr(
        integration, "_resolve_delivery_channel", lambda *a, **k: bare
    )

    assert integration._is_channel_ready("weixin", "user@im", instance_id="") is True


def test_live_instance_without_token_is_still_not_ready(monkeypatch):
    """A real, running instance that has never seen the receiver is genuinely
    not ready — we should defer, not blast into a login that can't route it."""
    live = _FakeChannel("weixin", "weixin-c6961093a5", tokens={})
    _install_manager(monkeypatch, _FakeManager({"weixin-c6961093a5": live}))
    _install_directory(monkeypatch, [])

    assert integration._is_channel_ready("weixin", "user@im", instance_id="") is False


# ── Backward-compatibility: legacy tasks with no instance_id / no agent_id ──
#
# Pre-existing tasks (created before multi-instance) store neither instance_id
# nor a per-instance login. They MUST keep delivering exactly as before. These
# tests pin that contract so a future change can't quietly break old data.


def test_legacy_single_instance_registers_under_channel_type(monkeypatch):
    """A non-multi install runs its channel under the bare channel_type key
    (``weixin``). A legacy task with no instance_id resolves to it via
    ``lookup = instance_id or channel_type`` — the original single-bot path."""
    legacy = _FakeChannel("weixin", "weixin", tokens={"user@im": "tok"})
    _install_manager(monkeypatch, _FakeManager({"weixin": legacy}))
    _install_directory(monkeypatch, [])

    resolved = integration._resolve_delivery_channel("weixin", "", "user@im")

    assert resolved is legacy
    assert integration._is_channel_ready("weixin", "user@im", instance_id="") is True


def test_no_manager_falls_back_to_create_channel_like_before(monkeypatch):
    """Before ChannelManager exists (or any failure reaching it), resolution
    must fall back to ``create_channel(channel_type)`` — byte-for-byte the old
    behaviour, so a solo install and old tasks are untouched."""
    import common.channel_registry as registry

    monkeypatch.setattr(registry, "get_channel_manager", lambda: None)

    bare = object()
    fake_factory = types.ModuleType("channel.channel_factory")
    called = {}

    def _create(channel_type, *a, **k):
        called["channel_type"] = channel_type
        return bare

    fake_factory.create_channel = _create
    monkeypatch.setitem(sys.modules, "channel.channel_factory", fake_factory)

    resolved = integration._resolve_delivery_channel("feishu", "", "ou_x")

    assert resolved is bare
    assert called["channel_type"] == "feishu"


def test_legacy_feishu_task_without_instance_id_single_instance(monkeypatch):
    """The common legacy case: one Feishu app, an old task with no instance_id
    and no directory entry. Auto-picking the sole running instance is safe and
    keeps the task delivering."""
    only = _FakeChannel("feishu", "feishu")
    _install_manager(monkeypatch, _FakeManager({"feishu": only}))
    _install_directory(monkeypatch, [])

    resolved = integration._resolve_delivery_channel("feishu", "", "ou_f1cbd4")

    assert resolved is only


def test_comma_joined_channel_type_is_normalized(monkeypatch):
    """config.json permits ``channel_type='web,feishu'``; a task copied from it
    stores that whole string. Readiness/resolution must not choke on it — the
    primary type is taken so the task still resolves instead of raising."""
    assert integration._primary_channel_type("feishu,dingtalk") == "feishu"
    assert integration._primary_channel_type("") == "unknown"
    assert integration._primary_channel_type(None) == "unknown"


def test_unknown_channel_type_is_always_ready(monkeypatch):
    """A task with a missing/unknown channel_type must not be blocked by the
    readiness probe (unknown -> True), preserving pre-check behaviour."""
    assert integration._is_channel_ready("", "whoever") is True
    assert integration._is_channel_ready("unknown", "whoever") is True


class _FakeWebChannel:
    """A web channel with no live polling queue (e.g. just after a restart)."""

    channel_type = "web"
    instance_id = "web"

    def __init__(self):
        self.session_queues = {}

    def has_session_queue(self, session_id, agent_id=None):
        return False


def test_web_is_ready_even_without_session_queue(monkeypatch):
    """A web session is always a valid delivery target: the message is persisted
    to history and an idle client keeps polling, so readiness must not gate on
    the in-memory session_queues. Gating there used to defer a scheduled push
    forever after a restart, even with the session and polling client present."""
    web = _FakeWebChannel()
    _install_manager(monkeypatch, _FakeManager({"web": web}))
    _install_directory(monkeypatch, [])

    assert integration._is_channel_ready("web", "session_abc", instance_id="web") is True


def test_directory_lookup_failure_does_not_break_resolution(monkeypatch):
    """If the recipient directory is unreadable, resolution must degrade
    gracefully (fall through), never raise into the scheduler tick."""
    only = _FakeChannel("feishu", "feishu")
    _install_manager(monkeypatch, _FakeManager({"feishu": only}))

    def _boom():
        raise OSError("directory unavailable")

    monkeypatch.setattr(integration, "_get_shared_recipient_store", _boom)

    # Single instance -> still resolves despite the directory blowing up.
    resolved = integration._resolve_delivery_channel("feishu", "", "ou_f1cbd4")
    assert resolved is only
