"""Ownership of a scheduled task follows its delivery channel instance.

A channel instance binds to exactly one Agent. An IM task delivers *through* an
instance, so the Agent it runs as (and the owner the console shows) is derived
live from that instance's current binding — never a value frozen on the task.
This is what lets an instance be re-bound to another Agent with zero task
migration, and keeps the edit form / task card honest the moment the delivery
instance is switched.
"""

import types

import agent.tools.scheduler.integration as integration
from agent.tools.scheduler.integration import effective_task_agent_id


class _FakeInstance:
    def __init__(self, agent_id):
        self.agent_id = agent_id


class _FakeRegistry:
    """Minimal registry: knows a fixed set of enabled agent ids + a default."""

    def __init__(self, agents, default_id):
        self._agents = set(agents)
        self.default_agent_id = default_id

    def get(self, agent_id, require_enabled=False):
        if agent_id in self._agents:
            return types.SimpleNamespace(id=agent_id)
        raise KeyError(agent_id)


def _bind_instances(monkeypatch, mapping):
    """Point ``get_instance`` at a fixed instance_id -> agent_id map."""
    import channel.channel_instances as ci

    def _get_instance(_settings, instance_id):
        agent_id = mapping.get(instance_id)
        return _FakeInstance(agent_id) if agent_id is not None else None

    monkeypatch.setattr(ci, "get_instance", _get_instance)
    monkeypatch.setattr("config.conf", lambda: {}, raising=False)


def _im_task(instance_id, channel_type="feishu", stored_agent_id=""):
    return {
        "id": "t1",
        "agent_id": stored_agent_id,
        "action": {
            "type": "agent_task",
            "task_description": "x",
            "channel_type": channel_type,
            "instance_id": instance_id,
            "receiver": "u1",
        },
    }


def test_im_task_owner_follows_the_instance_not_the_stored_value(monkeypatch):
    # The instance is bound to "beta"; the task still carries a stale "alpha".
    _bind_instances(monkeypatch, {"feishu-1": "beta"})
    registry = _FakeRegistry({"alpha", "beta"}, default_id="alpha")
    task = _im_task("feishu-1", stored_agent_id="alpha")

    assert effective_task_agent_id(task, registry) == "beta"


def test_rebinding_the_instance_moves_the_task_with_no_rewrite(monkeypatch):
    registry = _FakeRegistry({"alpha", "beta"}, default_id="alpha")
    task = _im_task("feishu-1", stored_agent_id="alpha")

    _bind_instances(monkeypatch, {"feishu-1": "alpha"})
    assert effective_task_agent_id(task, registry) == "alpha"

    # Re-bind the same instance; the task dict is untouched but ownership flips.
    _bind_instances(monkeypatch, {"feishu-1": "beta"})
    assert effective_task_agent_id(task, registry) == "beta"
    assert task["agent_id"] == "alpha"  # storage never rewritten


def test_unbound_instance_falls_back_to_the_stored_owner(monkeypatch):
    # Instance exists but has no explicit binding (agent_id empty) -> stored wins.
    _bind_instances(monkeypatch, {"feishu-1": ""})
    registry = _FakeRegistry({"alpha", "beta"}, default_id="alpha")
    task = _im_task("feishu-1", stored_agent_id="beta")

    assert effective_task_agent_id(task, registry) == "beta"


def test_web_task_keeps_its_stored_owner(monkeypatch):
    _bind_instances(monkeypatch, {})
    registry = _FakeRegistry({"alpha", "beta"}, default_id="alpha")
    task = {
        "id": "w1",
        "agent_id": "beta",
        "action": {"type": "send_message", "channel_type": "web", "receiver": "s1"},
    }

    assert effective_task_agent_id(task, registry) == "beta"


def test_execution_degrades_to_default_when_instance_binds_disabled_agent(monkeypatch):
    # Instance binds "ghost", who is not an enabled Agent. Execution must not run
    # as a phantom identity: validate=True degrades to the default.
    _bind_instances(monkeypatch, {"feishu-1": "ghost"})
    registry = _FakeRegistry({"alpha"}, default_id="alpha")
    task = _im_task("feishu-1", stored_agent_id="alpha")

    class _Bridge:
        agent_registry = registry

    assert integration._resolve_task_agent_id(_Bridge(), task) == "alpha"


def test_display_keeps_stored_owner_without_a_live_registry(monkeypatch):
    # Display path (validate=False) tolerates a missing registry: the owner is a
    # label, so a task keeps showing its stored agent_id in bare contexts.
    _bind_instances(monkeypatch, {})
    task = {
        "id": "n1",
        "agent_id": "research",
        "action": {"type": "agent_task", "task_description": "x"},
    }

    assert effective_task_agent_id(task, registry=None) == "research"
