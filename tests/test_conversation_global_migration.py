"""Regression tests for folding every Agent's conversations into the one
global ``index.db`` (the default Agent's file), told apart by an ``agent_id``
column.

Covers the three real-world upgrade paths the migration must survive:

1. **Single-Agent upgrade** — the vast majority. The lone (default) Agent's
   existing rows must keep working with zero data movement; they simply gain an
   empty ``agent_id`` that reads back as the default Agent.
2. **Multi-Agent merge with a shared session_id** — the hard case. Two Agents
   that used the same ``session_id`` in separate files must land in the global
   file without colliding, thanks to the composite ``(agent_id, session_id)``
   key.
3. **Idempotent re-run** — a second startup must not double-import or corrupt
   anything; the ``_migration_meta`` marker and the archived source tables both
   guard against it.
"""

import sqlite3
from pathlib import Path

import pytest

from agent.memory import (
    clear_conversation_store_cache,
    get_conversation_store,
    migrate_conversations_to_global,
)
from agent.registry import AgentProfile, AgentRegistry, set_agent_registry


def _message(text):
    return {"role": "user", "content": [{"type": "text", "text": text}]}


def _seed_legacy_db(workspace: Path, session_id: str, text: str) -> None:
    """Write a pre-global (old-schema) conversation DB into a workspace.

    Uses the single-column primary key and no ``agent_id`` column, i.e. exactly
    what a database created before this feature looks like.
    """
    db_dir = workspace / "memory" / "long-term"
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_dir / "index.db"))
    try:
        conn.executescript(
            """
            CREATE TABLE sessions (
                session_id        TEXT PRIMARY KEY,
                channel_type      TEXT NOT NULL DEFAULT '',
                title             TEXT NOT NULL DEFAULT '',
                context_start_seq INTEGER NOT NULL DEFAULT 0,
                created_at        INTEGER NOT NULL,
                last_active       INTEGER NOT NULL,
                msg_count         INTEGER NOT NULL DEFAULT 0,
                pinned            INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                seq        INTEGER NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                extras     TEXT NOT NULL DEFAULT '',
                run_id     TEXT NOT NULL DEFAULT '',
                UNIQUE (session_id, seq)
            );
            """
        )
        conn.execute(
            "INSERT INTO sessions (session_id, channel_type, created_at, last_active, msg_count) "
            "VALUES (?, 'feishu', 1, 1, 1)",
            (session_id,),
        )
        conn.execute(
            "INSERT INTO messages (session_id, seq, role, content, created_at) "
            "VALUES (?, 0, 'user', ?, 1)",
            (session_id, f'[{{"type":"text","text":"{text}"}}]'),
        )
        conn.commit()
    finally:
        conn.close()


def _install_registry(tmp_path, agent_ids, default_id):
    registry = AgentRegistry(
        [AgentProfile(a, a.title(), str(tmp_path / a)) for a in agent_ids],
        default_agent_id=default_id,
    )
    set_agent_registry(registry)
    clear_conversation_store_cache()
    return registry


@pytest.fixture
def restore_registry():
    yield
    # ``None`` rather than the instance from before the test: set_agent_registry
    # pins process-wide, so putting that instance back would leave configuration
    # changes ignored and every later test resolving to this test's workspace.
    set_agent_registry(None)
    clear_conversation_store_cache()


def test_single_agent_upgrade_keeps_history_with_zero_movement(tmp_path, restore_registry):
    # One default Agent with a legacy DB already holding a conversation.
    _install_registry(tmp_path, ["default"], "default")
    default_ws = tmp_path / "default"
    _seed_legacy_db(default_ws, "user-1", "hello")

    migrate_conversations_to_global(kickoff_async=False)

    store = get_conversation_store(str(default_ws))
    # The row is still there, read back through the (now agent-scoped) store.
    msgs = store.load_messages("user-1")
    assert msgs and msgs[0]["content"][0]["text"] == "hello"
    # The default Agent scopes to "" and the file did not move.
    assert store._agent_id == ""
    assert Path(store._db_path) == default_ws / "memory" / "long-term" / "index.db"


def test_multi_agent_merge_survives_shared_session_id(tmp_path, restore_registry):
    # Default + one secondary Agent, both with a legacy DB, both using the SAME
    # session_id -- the collision the composite key exists to handle.
    _install_registry(tmp_path, ["default", "research"], "default")
    default_ws = tmp_path / "default"
    research_ws = tmp_path / "research"
    _seed_legacy_db(default_ws, "shared", "from-default")
    _seed_legacy_db(research_ws, "shared", "from-research")

    migrate_conversations_to_global(kickoff_async=False)

    default_store = get_conversation_store(str(default_ws))
    research_store = get_conversation_store(str(research_ws))

    # Same session_id, no collision: each Agent reads its own message.
    assert default_store.load_messages("shared")[0]["content"][0]["text"] == "from-default"
    assert research_store.load_messages("shared")[0]["content"][0]["text"] == "from-research"
    # Both back onto the one global file.
    global_db = default_ws / "memory" / "long-term" / "index.db"
    assert Path(default_store._db_path) == global_db
    assert Path(research_store._db_path) == global_db

    # The secondary Agent's source tables were archived, not dropped, and the
    # merge was marked done so it never repeats.
    src = sqlite3.connect(str(research_ws / "memory" / "long-term" / "index.db"))
    try:
        tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        src.close()
    assert any(t.startswith("sessions_migrated_") for t in tables)
    assert "sessions" not in tables  # renamed aside


def test_merge_is_idempotent_across_restarts(tmp_path, restore_registry):
    _install_registry(tmp_path, ["default", "research"], "default")
    default_ws = tmp_path / "default"
    research_ws = tmp_path / "research"
    _seed_legacy_db(default_ws, "d1", "default-msg")
    _seed_legacy_db(research_ws, "r1", "research-msg")

    # First startup.
    migrate_conversations_to_global(kickoff_async=False)
    # Second startup: must be a no-op, never double-import.
    clear_conversation_store_cache()
    migrate_conversations_to_global(kickoff_async=False)

    research_store = get_conversation_store(str(research_ws))
    msgs = research_store.load_messages("r1")
    # Exactly one message, not duplicated by the second run.
    assert len(msgs) == 1
    assert msgs[0]["content"][0]["text"] == "research-msg"

    # The marker records the completed merge.
    global_db = default_ws / "memory" / "long-term" / "index.db"
    conn = sqlite3.connect(str(global_db))
    try:
        marked = conn.execute(
            "SELECT 1 FROM _migration_meta WHERE key = 'merged_agent:research'"
        ).fetchone()
    finally:
        conn.close()
    assert marked is not None


def test_multi_agent_secondary_writes_never_split_into_source(tmp_path, restore_registry):
    """Regression for the pm-agent split: on a multi-Agent install, a secondary
    Agent's writes must land in the global file even when the store is opened by
    its own workspace path. Never in the soon-to-be-archived source file, which
    would resurface as empty recreated tables + orphaned rows."""
    _install_registry(tmp_path, ["default", "pm-agent"], "default")
    default_ws = tmp_path / "default"
    # pm-agent's real workspace under agents/<id>/, matching the registry layout.
    pm_ws = tmp_path / "pm-agent"

    store = get_conversation_store(str(pm_ws))
    store.append_messages("s-new", [_message("written after global cutover")])

    # It wrote to the GLOBAL file, tagged pm-agent...
    global_db = default_ws / "memory" / "long-term" / "index.db"
    assert Path(store._db_path) == global_db
    assert store._agent_id == "pm-agent"
    assert store.load_messages("s-new")[0]["content"][0]["text"] == "written after global cutover"

    # ...and did NOT create a stray conversation DB in pm-agent's own workspace.
    assert not (pm_ws / "memory" / "long-term" / "index.db").exists()


def test_unmatched_agents_layout_workspace_binds_global_by_derived_id(tmp_path, restore_registry):
    """A workspace the registry doesn't claim but that sits under agents/<id>/
    still binds to the global file, with the id derived from the path — never
    its own (archivable) file."""
    # Two agents so we're firmly in the multi-Agent regime.
    _install_registry(tmp_path, ["default", "pm-agent"], "default")
    default_ws = tmp_path / "default"
    # A workspace not in the registry, laid out as agents/ghost/.
    ghost_ws = tmp_path / "agents" / "ghost"

    store = get_conversation_store(str(ghost_ws))
    global_db = default_ws / "memory" / "long-term" / "index.db"
    assert Path(store._db_path) == global_db
    assert store._agent_id == "ghost"  # derived from the agents/<id>/ layout
    assert not (ghost_ws / "memory" / "long-term" / "index.db").exists()


def test_secondary_agent_store_binds_global_even_under_identity_scope(tmp_path, restore_registry):
    """Regression for the pm-agent split: opening the store while the ambient
    RuntimeIdentity is a NON-default Agent (as AgentInitializer does mid-turn)
    must still bind the global default file — not that Agent's own, soon-to-be-
    archived source DB. The bug was `_default_db_path()` resolving through the
    routing-aware config, which returned the routed Agent's file."""
    from common.runtime_identity import identity_scope

    _install_registry(tmp_path, ["default", "pm-agent"], "default")
    default_ws = tmp_path / "default"
    pm_ws = tmp_path / "pm-agent"
    global_db = default_ws / "memory" / "long-term" / "index.db"

    # Explicit workspace, under a pm-agent identity scope.
    with identity_scope(agent_id="pm-agent"):
        s1 = get_conversation_store(str(pm_ws))
        # No-arg, routing-aware, also under the pm-agent scope.
        s2 = get_conversation_store()

    for s in (s1, s2):
        assert Path(s._db_path) == global_db, f"bound {s._db_path}, expected global"
        assert s._agent_id == "pm-agent"
    assert not (pm_ws / "memory" / "long-term" / "index.db").exists()
