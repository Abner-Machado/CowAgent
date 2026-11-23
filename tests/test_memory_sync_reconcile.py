# encoding:utf-8
"""sync() must drop index rows whose file left the scan set.

sync() only ever added and overwrote: ``delete_by_path`` was called on the
file about to be rewritten, and nothing ever removed a row for a file that was
gone. So a deleted knowledge page stayed searchable forever, and an Agent
switched from the shared knowledge base to its own kept every shared page in
its index — memory_search went on returning "knowledge/..." hits that
memory_get and read (correctly scoped to the private root) could not open.

The reconcile pass has to run even when no file changed, because a stale index
is exactly the case where nothing changed and there is nothing to embed.
"""

import asyncio
from pathlib import Path

import pytest

from agent.memory.config import MemoryConfig
from agent.memory.manager import MemoryManager


def _manager(workspace: Path) -> MemoryManager:
    manager = MemoryManager(config=MemoryConfig(workspace_root=str(workspace)))
    manager._init_workspace()
    return manager


def _indexed(manager: MemoryManager, source: str) -> set:
    return set(manager.storage.list_paths(source))


@pytest.fixture
def shared(tmp_path, monkeypatch):
    """A shared root outside the workspace, as _shared_or_own resolves it."""
    root = tmp_path / "shared"
    (root / "knowledge").mkdir(parents=True)
    monkeypatch.setattr("common.state_dir.shared_root", lambda: root)
    return root


def test_a_deleted_knowledge_page_stops_being_indexed(tmp_path, shared):
    workspace = tmp_path / "workspace"
    (workspace / "knowledge").mkdir(parents=True)
    keep = workspace / "knowledge" / "keep.md"
    gone = workspace / "knowledge" / "gone.md"
    keep.write_text("# keep\nGLACIERQUARTZ7731\n", encoding="utf-8")
    gone.write_text("# gone\nTOPAZLANTERN4419\n", encoding="utf-8")

    manager = _manager(workspace)
    asyncio.run(manager.sync())
    assert _indexed(manager, "knowledge") == {"knowledge/keep.md", "knowledge/gone.md"}

    gone.unlink()
    # keep.md is untouched, so this sync has nothing to embed. Reconcile still
    # has to happen, which is what the early "nothing pending" return used to
    # skip past.
    asyncio.run(manager.sync())

    assert _indexed(manager, "knowledge") == {"knowledge/keep.md"}
    assert manager.storage.get_file_hash("knowledge/gone.md") is None


def test_going_exclusive_drops_the_shared_pages(tmp_path, shared):
    """The Agent's own knowledge/ replaces the shared base it fell back to."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (shared / "knowledge" / "shared-page.md").write_text(
        "# shared\nGLACIERQUARTZ7731\n", encoding="utf-8"
    )

    manager = _manager(workspace)
    asyncio.run(manager.sync())
    assert _indexed(manager, "knowledge") == {"knowledge/shared-page.md"}

    # Opting out is by presence: creating knowledge/ makes the Agent exclusive.
    (workspace / "knowledge").mkdir()
    (workspace / "knowledge" / "own-page.md").write_text(
        "# own\nTOPAZLANTERN4419\n", encoding="utf-8"
    )
    asyncio.run(manager.sync())

    # The shared page is not merely unreachable by read/memory_get now — it is
    # out of the index, so memory_search cannot surface it either.
    assert _indexed(manager, "knowledge") == {"knowledge/own-page.md"}


def test_going_shared_drops_the_private_pages(tmp_path, shared):
    """And back the other way, without a switch hook to tell sync it happened."""
    workspace = tmp_path / "workspace"
    (workspace / "knowledge").mkdir(parents=True)
    (workspace / "knowledge" / "own-page.md").write_text(
        "# own\nTOPAZLANTERN4419\n", encoding="utf-8"
    )
    (shared / "knowledge" / "shared-page.md").write_text(
        "# shared\nGLACIERQUARTZ7731\n", encoding="utf-8"
    )

    manager = _manager(workspace)
    asyncio.run(manager.sync())
    assert _indexed(manager, "knowledge") == {"knowledge/own-page.md"}

    import shutil
    shutil.rmtree(workspace / "knowledge")
    asyncio.run(manager.sync())

    assert _indexed(manager, "knowledge") == {"knowledge/shared-page.md"}


def test_a_deleted_memory_note_stops_being_indexed(tmp_path, shared):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    manager = _manager(workspace)
    notes = manager.config.get_memory_dir()
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "2026-09-20.md").write_text("# today\nTOPAZLANTERN4419\n", encoding="utf-8")

    asyncio.run(manager.sync())
    assert any(p.endswith("2026-09-20.md") for p in _indexed(manager, "memory"))

    (notes / "2026-09-20.md").unlink()
    asyncio.run(manager.sync())

    assert not any(p.endswith("2026-09-20.md") for p in _indexed(manager, "memory"))


def test_an_unresolvable_root_does_not_cost_the_index(tmp_path, shared, monkeypatch):
    """An empty scan set must mean "the files are gone", not "the root moved".

    Reconcile is gated on the root existing, so a knowledge base that is
    temporarily not there leaves the rows alone instead of forcing a full
    re-embed once it comes back.
    """
    workspace = tmp_path / "workspace"
    (workspace / "knowledge").mkdir(parents=True)
    (workspace / "knowledge" / "page.md").write_text(
        "# page\nGLACIERQUARTZ7731\n", encoding="utf-8"
    )

    manager = _manager(workspace)
    asyncio.run(manager.sync())
    assert _indexed(manager, "knowledge") == {"knowledge/page.md"}

    missing = tmp_path / "not-mounted-yet"
    monkeypatch.setattr("common.state_dir.knowledge_dir", lambda **kw: missing)
    asyncio.run(manager.sync())

    assert _indexed(manager, "knowledge") == {"knowledge/page.md"}


def test_a_symlinked_knowledge_root_is_not_mistaken_for_an_empty_one(tmp_path, shared):
    """Pointing knowledge/ at the shared base with a symlink is a real setup.

    Such an Agent counts as exclusive (the path exists) while its files are the
    shared ones. Whatever walks the root has to follow the link: a walker that
    does not would hand reconcile an empty scan set for a root that exists, and
    every page the Agent has would be dropped from its index.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (shared / "knowledge" / "shared-page.md").write_text(
        "# shared\nGLACIERQUARTZ7731\n", encoding="utf-8"
    )
    (workspace / "knowledge").symlink_to(shared / "knowledge", target_is_directory=True)

    manager = _manager(workspace)
    asyncio.run(manager.sync())
    assert _indexed(manager, "knowledge") == {"knowledge/shared-page.md"}

    asyncio.run(manager.sync())

    assert _indexed(manager, "knowledge") == {"knowledge/shared-page.md"}


def test_a_present_but_unreadable_page_keeps_its_rows(tmp_path, shared):
    """Unreadable is not gone: the file is still there, so the rows stand."""
    workspace = tmp_path / "workspace"
    (workspace / "knowledge").mkdir(parents=True)
    page = workspace / "knowledge" / "page.md"
    page.write_text("# page\nGLACIERQUARTZ7731\n", encoding="utf-8")

    manager = _manager(workspace)
    asyncio.run(manager.sync())
    assert _indexed(manager, "knowledge") == {"knowledge/page.md"}

    page.write_bytes(b"\xff\xfe\x00 not utf-8 \xff")
    asyncio.run(manager.sync())

    assert _indexed(manager, "knowledge") == {"knowledge/page.md"}
