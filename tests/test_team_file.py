"""The roster's own file: migration off config.json, and staying readable."""

import json

import pytest

from agent import team
from agent.admin import AgentAdminService
from agent.registry import AgentRegistry, set_agent_registry


@pytest.fixture
def install(tmp_path):
    """An install that predates the roster file, with everything in config.json.

    Laid out the way a real one is: the default Agent owns the instance root,
    and config.json sits outside it in the data root.
    """
    root = tmp_path / "cow"
    root.mkdir()
    config = tmp_path / "data" / "config.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            {
                "agent_workspace": str(root),
                "model": "a-setting-owned-by-another-page",
                "default_agent_id": "primary",
                "agents": [{"id": "primary", "name": "Primary", "workspace": str(root)}],
                "channel_instances": [
                    {"instance_id": "feishu", "channel_type": "feishu", "agent_id": "primary"}
                ],
            }
        ),
        encoding="utf-8",
    )
    set_agent_registry(None)
    try:
        yield AgentAdminService(str(config)), root, config
    finally:
        set_agent_registry(None)


def _settings(root):
    return {"agent_workspace": str(root)}


class TestAnInstallThatPredatesTheFile:
    def test_it_keeps_working_with_no_file_at_all(self, install):
        service, root, _ = install
        assert not team.team_file(_settings(root)).exists()
        assert [item["id"] for item in service.snapshot()["agents"]] == ["primary"]

    def test_the_first_edit_moves_it_out(self, install):
        service, root, config = install

        service.create_agent("research", "Research")

        moved = json.loads((root / "agents" / "team.json").read_text(encoding="utf-8"))
        assert [item["id"] for item in moved["agents"]] == ["primary", "research"]
        assert moved["channel_instances"] == [
            {"instance_id": "feishu", "channel_type": "feishu", "agent_id": "primary"}
        ]

    def test_the_old_copy_is_removed_so_nobody_edits_the_wrong_one(self, install):
        service, _, config = install

        service.create_agent("research", "Research")

        remaining = json.loads(config.read_text(encoding="utf-8"))
        assert not any(key in remaining for key in team.TEAM_KEYS)
        assert remaining["model"] == "a-setting-owned-by-another-page"


class TestSurvivingAMove:
    """The file sits with the workspaces, so it must not pin them by path."""

    def test_a_standard_layout_is_written_without_any_paths(self, install):
        service, root, _ = install

        service.create_agent("research", "Research")

        stored = json.loads((root / "agents" / "team.json").read_text(encoding="utf-8"))
        assert not any("workspace" in item for item in stored["agents"])

    def test_the_whole_tree_can_be_moved_and_still_resolves(self, install, tmp_path):
        service, root, _ = install
        service.create_agent("research", "Research")

        moved = tmp_path / "moved-cow"
        root.rename(moved)

        registry = AgentRegistry.from_config(team.resolve(_settings(moved)))
        assert registry.get("research").workspace == str(moved / "agents" / "research")

    def test_an_agent_parked_elsewhere_keeps_its_path(self, install, tmp_path):
        service, root, _ = install
        outside = tmp_path / "other-disk" / "research"

        service.create_agent("research", "Research", str(outside))

        stored = json.loads((root / "agents" / "team.json").read_text(encoding="utf-8"))
        parked = next(item for item in stored["agents"] if item["id"] == "research")
        assert parked["workspace"] == str(outside.resolve())


class TestWhenTheFileCannotBeRead:
    """Losing the roster would look like every Agent had been deleted, so a
    damaged file falls back rather than starting from nothing."""

    def test_a_corrupt_file_falls_back_to_config_json(self, install):
        service, root, _ = install
        (root / "agents").mkdir(parents=True, exist_ok=True)
        (root / "agents" / "team.json").write_text("{ not json", encoding="utf-8")

        assert [item["id"] for item in service.snapshot()["agents"]] == ["primary"]

    def test_a_file_that_is_not_an_object_falls_back_too(self, install):
        service, root, _ = install
        (root / "agents").mkdir(parents=True, exist_ok=True)
        (root / "agents" / "team.json").write_text("[]", encoding="utf-8")

        assert [item["id"] for item in service.snapshot()["agents"]] == ["primary"]


class TestCachingTheRegistry:
    def test_the_signature_follows_the_file(self, install):
        service, root, _ = install
        before = team.stamp(_settings(root))

        service.create_agent("research", "Research")

        assert team.stamp(_settings(root)) != before

    def test_the_signature_follows_config_json_while_it_is_still_the_source(self, install):
        _, root, _ = install
        legacy = dict(_settings(root))
        legacy["agents"] = [{"id": "primary"}]
        assert team.stamp(legacy) != team.stamp(_settings(root))


class TestMigratingAtStartup:
    """Waiting for an edit leaves the roster in config.json indefinitely, still
    exposed to every caller that rewrites that file wholesale."""

    def test_startup_moves_it_without_anyone_editing_anything(self, install):
        _, root, config = install
        settings = json.loads(config.read_text(encoding="utf-8"))

        written = team.migrate(settings, config)

        assert written == team.team_file(_settings(root))
        moved = json.loads(written.read_text(encoding="utf-8"))
        assert [item["id"] for item in moved["agents"]] == ["primary"]
        assert moved["default_agent_id"] == "primary"
        assert moved["channel_instances"] == [
            {"instance_id": "feishu", "channel_type": "feishu", "agent_id": "primary"}
        ]

    def test_config_keeps_what_is_actually_its_own(self, install):
        _, _, config = install
        settings = json.loads(config.read_text(encoding="utf-8"))

        team.migrate(settings, config)

        left = json.loads(config.read_text(encoding="utf-8"))
        assert left["model"] == "a-setting-owned-by-another-page"
        assert left["agent_workspace"]
        assert not any(key in left for key in team.TEAM_KEYS)

    def test_a_derivable_workspace_is_not_written_out(self, install):
        """Absolute paths in the file would not survive moving the install."""
        _, root, config = install
        settings = json.loads(config.read_text(encoding="utf-8"))

        written = team.migrate(settings, config)

        assert "workspace" not in json.loads(written.read_text(encoding="utf-8"))["agents"][0]

    def test_running_it_again_is_a_no_op(self, install):
        _, root, config = install
        settings = json.loads(config.read_text(encoding="utf-8"))
        written = team.migrate(settings, config)
        before = written.read_text(encoding="utf-8")

        assert team.migrate(json.loads(config.read_text(encoding="utf-8")), config) is None
        assert written.read_text(encoding="utf-8") == before

    def test_a_single_agent_install_gets_no_file(self, tmp_path):
        """Nothing to move, so nothing appears that was not there before."""
        root = tmp_path / "cow"
        root.mkdir()
        settings = {"agent_workspace": str(root), "model": "gpt-x"}

        assert team.migrate(settings, None) is None
        assert not team.team_file(settings).exists()
        assert not (root / "agents").exists()
