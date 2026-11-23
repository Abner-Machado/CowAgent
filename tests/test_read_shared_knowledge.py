"""`read` accepts the "knowledge/..." spelling its Agent is handed.

An Agent with no ``knowledge/`` of its own reads the shared copy, which sits
outside the workspace relative paths resolve against. memory_search results and
the links in index.md still name those pages as ``knowledge/...``, so a read of
one used to miss. The retry runs only where the read already failed, which is
what the first class below pins down.
"""

import os
from pathlib import Path

import pytest

from agent.tools.read.read import Read


def _text(result):
    """What the model would see: a dict of lines on success, a string on error."""
    body = result.result
    return body if isinstance(body, str) else body.get("content", "")


@pytest.fixture
def agent(tmp_path, monkeypatch):
    """An Agent whose knowledge lives in the shared root, not its workspace."""
    from common import state_dir

    shared_root = tmp_path / "cow" / "knowledge"
    (shared_root / "entities").mkdir(parents=True)
    (shared_root / "entities" / "linkai.md").write_text("# LinkAI\nshared page\n")

    workspace = tmp_path / "cow" / "agents" / "pm-agent"
    workspace.mkdir(parents=True)

    def fake_knowledge_dir(base=None, ensure=False):
        own = Path(base) / "knowledge"
        return own if own.is_dir() else shared_root

    monkeypatch.setattr(state_dir, "knowledge_dir", fake_knowledge_dir)
    return Read({"cwd": str(workspace)}), shared_root, workspace


class TestNothingThatResolvesTodayChanges:
    """The retry must only ever turn a failure into a success."""

    def test_a_workspace_file_still_wins(self, agent):
        tool, shared_root, workspace = agent
        # Same relative path exists in both roots. The workspace copy resolves
        # first, so the fallback is never consulted and the Agent keeps reading
        # its own page.
        own = workspace / "knowledge" / "entities"
        own.mkdir(parents=True)
        (own / "linkai.md").write_text("# LinkAI\nlocal page\n")

        result = tool.execute({"path": "knowledge/entities/linkai.md"})
        assert "local page" in _text(result)
        assert "shared page" not in _text(result)

    def test_an_ordinary_miss_still_reports_the_workspace_path(self, agent):
        tool, _, workspace = agent
        result = tool.execute({"path": "notes/absent.md"})
        assert result.status == "error"
        assert "File not found" in _text(result)
        assert str(workspace) in _text(result)

    def test_a_knowledge_miss_in_both_roots_still_fails(self, agent):
        tool, _, _ = agent
        result = tool.execute({"path": "knowledge/entities/absent.md"})
        assert result.status == "error"
        assert "File not found" in _text(result)


class TestTheFallback:
    def test_a_shared_page_opens_under_its_logical_path(self, agent):
        tool, _, _ = agent
        result = tool.execute({"path": "knowledge/entities/linkai.md"})
        assert result.status == "success"
        assert "shared page" in _text(result)

    def test_traversal_is_not_a_way_out_of_the_shared_root(self, agent, tmp_path):
        tool, _, _ = agent
        secret = tmp_path / "secret.md"
        secret.write_text("KEEP-THIS-OUT\n")
        # The retry means a page under the shared root, never a lever for
        # naming files elsewhere through it.
        result = tool.execute({"path": "knowledge/../../../secret.md"})
        assert result.status == "error"
        assert "KEEP-THIS-OUT" not in _text(result)

    def test_a_bare_knowledge_path_is_not_enough_to_trigger_it(self, agent):
        tool, _, _ = agent
        # One segment names the directory itself, not a page; nothing to retry.
        result = tool.execute({"path": "knowledge"})
        assert result.status == "error"

    def test_an_unresolvable_root_leaves_the_original_error(self, agent, monkeypatch):
        tool, _, _ = agent
        from common import state_dir

        def boom(base=None, ensure=False):
            raise RuntimeError("registry not ready")

        monkeypatch.setattr(state_dir, "knowledge_dir", boom)
        result = tool.execute({"path": "knowledge/entities/linkai.md"})
        assert result.status == "error"
        assert "File not found" in _text(result)
