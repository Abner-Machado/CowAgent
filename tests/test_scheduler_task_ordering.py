"""Task-list ordering: a freshly created task shows at the top.

The console lists tasks enabled-first, then newest-created on top — so a task the
user just created is at the head of the list rather than wherever its next run
time happens to fall. Disabled tasks sink to the bottom of their own group.
"""

import os
import tempfile

from agent.tools.scheduler.task_store import TaskStore


def _store():
    tmp = tempfile.mkdtemp()
    return TaskStore(os.path.join(tmp, "tasks.json"))


def _task(tid, created, enabled=True, next_run=""):
    return {
        "id": tid,
        "name": tid,
        "enabled": enabled,
        "created_at": created,
        "next_run_at": next_run,
        "schedule": {"type": "cron", "expression": "0 9 * * *"},
        "action": {"type": "send_message", "content": "hi"},
    }


def test_newest_created_first_within_enabled():
    store = _store()
    # 'old' runs sooner than 'new', but 'new' was created later and must lead.
    store.add_task(_task("old", "2026-01-01T00:00:00", next_run="2026-01-01T09:00:00"))
    store.add_task(_task("new", "2026-03-01T00:00:00", next_run="2099-01-01T09:00:00"))
    order = [t["id"] for t in store.list_tasks()]
    assert order == ["new", "old"]


def test_disabled_sink_below_enabled_regardless_of_recency():
    store = _store()
    store.add_task(_task("enabled-old", "2026-01-01T00:00:00"))
    store.add_task(_task("disabled-newest", "2026-06-01T00:00:00", enabled=False))
    order = [t["id"] for t in store.list_tasks()]
    assert order == ["enabled-old", "disabled-newest"]


def test_missing_created_at_sorts_last_in_group():
    store = _store()
    store.add_task(_task("has-created", "2026-02-01T00:00:00"))
    legacy = _task("legacy", "")
    legacy.pop("created_at")
    store.add_task(legacy)
    order = [t["id"] for t in store.list_tasks()]
    assert order == ["has-created", "legacy"]
