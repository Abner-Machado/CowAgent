"""The knowledge root an Agent is told about must be the one its tools resolve.

An Agent with no ``knowledge/`` of its own reads the shared copy, which does not
sit under its workspace. Advertising a bare ``knowledge/`` in that case aims
every ``read`` at the workspace, where none of the pages are, so the Agent is
handed an index of pages it cannot open (#3175 follow-up).
"""

import os
from pathlib import Path

import pytest

from agent.prompt.builder import _knowledge_base_path
from agent.tools.memory.memory_search import MemorySearchTool


@pytest.fixture
def shared(tmp_path, monkeypatch):
    """A shared knowledge root plus a workspace that has no local copy."""
    from common import state_dir

    shared_root = tmp_path / "cow" / "knowledge"
    shared_root.mkdir(parents=True)
    workspace = tmp_path / "cow" / "agents" / "pm-agent"
    workspace.mkdir(parents=True)

    def fake_knowledge_dir(base=None, ensure=False):
        own = Path(base) / "knowledge"
        return own if own.is_dir() else shared_root

    monkeypatch.setattr(state_dir, "knowledge_dir", fake_knowledge_dir)
    return shared_root, workspace


class TestPromptPath:
    def test_an_agent_on_the_shared_copy_is_told_where_it_really_is(self, shared):
        shared_root, workspace = shared
        assert _knowledge_base_path(str(workspace)) == str(shared_root)

    def test_an_agent_with_its_own_copy_keeps_the_relative_form(self, shared):
        _, workspace = shared
        (workspace / "knowledge").mkdir()
        # Unchanged for the common single-Agent install, where the relative
        # spelling already resolves and is shorter to carry in the prompt.
        assert _knowledge_base_path(str(workspace)) == "knowledge"

    def test_no_workspace_is_not_worth_guessing_about(self):
        assert _knowledge_base_path("") == "knowledge"

    def test_an_unresolvable_root_falls_back_instead_of_breaking_the_prompt(
        self, tmp_path, monkeypatch
    ):
        from common import state_dir

        def boom(base=None, ensure=False):
            raise RuntimeError("registry not ready")

        monkeypatch.setattr(state_dir, "knowledge_dir", boom)
        # The prompt is built on every turn; a bad root must cost a worse path
        # than usual, never the section itself.
        assert _knowledge_base_path(str(tmp_path)) == "knowledge"


class _Result:
    def __init__(self, path):
        self.path = path


def _tool(workspace):
    class _Config:
        def get_workspace(self):
            return str(workspace)

    class _Manager:
        config = _Config()

    return MemorySearchTool(_Manager())


class TestSearchHint:
    def test_shared_paths_say_what_they_are_relative_to(self, shared):
        shared_root, workspace = shared
        hint = _tool(workspace)._knowledge_root_hint([_Result("knowledge/a.md")])
        # The prompt names this root too, but it is skipped entirely when there
        # is no index.md, and these paths mean nothing without it.
        assert hint is not None and str(shared_root) in hint

    def test_nothing_is_said_when_the_relative_path_already_resolves(self, shared):
        _, workspace = shared
        (workspace / "knowledge").mkdir()
        assert _tool(workspace)._knowledge_root_hint([_Result("knowledge/a.md")]) is None

    def test_nothing_is_said_when_no_hit_came_from_knowledge(self, shared):
        _, workspace = shared
        results = [_Result("MEMORY.md"), _Result("memory/2026-09-08.md")]
        assert _tool(workspace)._knowledge_root_hint(results) is None

    def test_a_broken_root_costs_the_hint_not_the_results(self, tmp_path, monkeypatch):
        from common import state_dir

        def boom(base=None, ensure=False):
            raise RuntimeError("registry not ready")

        monkeypatch.setattr(state_dir, "knowledge_dir", boom)
        tool = _tool(tmp_path)
        assert tool._knowledge_root_hint([_Result("knowledge/a.md")]) is None
