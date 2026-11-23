# encoding:utf-8
"""Index keys must be stable, and one bad file must not abort the sync.

Follow-up to #3175, where a single file sync() could not map to a key raised
out of the scan loop and took down the whole sync -- and with it every
retrieval that goes through the ``search()`` in front of it. Two properties
keep that class of failure from coming back, so both are pinned here: a file
that cannot be mapped is skipped rather than raised, and the key a file does
get does not depend on how its root happened to be spelled.
"""

import asyncio
from pathlib import Path

from agent.memory.config import MemoryConfig
from agent.memory.manager import MemoryManager, _index_rel_path


def test_knowledge_keeps_its_prefix_wherever_the_dir_lives(tmp_path):
    """A shared knowledge dir keys the same as a private one would."""
    shared_knowledge = tmp_path / "shared" / "knowledge"
    roots = [(shared_knowledge, "knowledge"), (tmp_path / "workspace", "")]

    key = _index_rel_path(shared_knowledge / "nested" / "note.md", roots)

    assert key == "knowledge/nested/note.md"


def test_workspace_files_are_keyed_relative_to_the_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    roots = [(workspace / "knowledge", "knowledge"), (workspace, "")]

    assert _index_rel_path(workspace / "memory" / "a.md", roots) == "memory/a.md"


def test_keys_are_posix_spelled_so_one_file_is_not_indexed_twice(tmp_path):
    key = _index_rel_path(tmp_path / "memory" / "users" / "wang" / "a.md", [(tmp_path, "")])

    # add_memory() writes "memory/users/<id>/..." literally, so sync() has to
    # agree with it on every platform instead of keying by os.sep.
    assert key == "memory/users/wang/a.md"
    assert "\\" not in key


def test_a_root_reached_through_a_symlink_still_matches(tmp_path):
    real = tmp_path / "real"
    (real / "knowledge").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real)

    # Root spelled through the symlink, file spelled through the real path.
    key = _index_rel_path(real / "knowledge" / "a.md", [(link / "knowledge", "knowledge")])

    assert key == "knowledge/a.md"


def test_a_file_under_no_known_root_is_skipped_not_raised(tmp_path):
    roots = [(tmp_path / "workspace", "")]

    assert _index_rel_path(tmp_path / "elsewhere" / "a.md", roots) is None


def test_one_unreadable_file_does_not_cost_the_agent_the_rest_of_its_memory(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    shared = tmp_path / "shared"
    knowledge = shared / "knowledge"
    knowledge.mkdir(parents=True)
    (knowledge / "good.md").write_text("# good\nHOLLOWMARBLE4412\n", encoding="utf-8")
    # A directory named like a markdown file: rglob("*.md") hands it to the
    # scan loop and read_text() raises on it.
    (knowledge / "broken.md").mkdir()

    monkeypatch.setattr("common.state_dir.shared_root", lambda: shared)
    manager = MemoryManager(config=MemoryConfig(workspace_root=str(workspace)))
    manager._init_workspace()

    asyncio.run(manager.sync())

    assert manager.storage.get_file_hash("knowledge/good.md") is not None
