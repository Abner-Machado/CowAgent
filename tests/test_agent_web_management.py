def test_web_backend_exposes_agent_and_core_file_routes():
    from conftest import web_backend_py
    source = web_backend_py()
    assert "'/api/agents', 'AgentsHandler'" in source
    assert "'/api/agents/([^/]+)/files/([^/]+)', 'AgentCoreFileHandler'" in source
    assert "'/api/agents/([^/]+)/avatar', 'AgentAvatarHandler'" in source
    assert "class AgentsHandler:" in source
    assert "class AgentCoreFileHandler:" in source
    assert "scope" in source and "_list_sessions_across_agents" in source


def test_console_has_agent_cards_not_a_tenant_switcher():
    # The page is assembled from templates/, so assert against what is served.
    from channel.web.core import template
    html = template.render("chat.html")
    assert 'id="agent-selector"' not in html
    # The team is a top-level view of its own now, not a Settings panel: it is
    # where you compose and manage the Agents you work with.
    assert 'data-view="agents"' in html
    assert 'id="view-agents"' in html
    assert 'id="agents-grid"' in html
    assert 'id="agent-core-editor"' in html
    assert 'id="composer-agent-btn"' in html
    # The core-file picker is the same dropdown component used elsewhere in the
    # console, not a native <select>; its options are built in JS from
    # _agentCoreFileOptions() rather than hardcoded <option> tags in markup.
    assert 'id="agent-core-file" class="cfg-dropdown cfg-dropdown-xs"' in html
    from conftest import console_js
    js = console_js()
    for filename in ("AGENT.md", "USER.md", "RULE.md", "MEMORY.md"):
        assert f"value: '{filename}'" in js
    # BOOTSTRAP.md is internal and deliberately left out of the hand-editable
    # picker.
    assert "value: 'BOOTSTRAP.md'" not in js


def test_console_carries_agent_id_through_existing_feature_requests():
    from conftest import console_js
    source = console_js()
    assert "body.agent_id = activeAgentId" in source
    assert "agent_id=${encodeURIComponent(activeAgentId)}" in source
    assert "function runtimeSessionKey" in source
    assert "scope=all" in source
    assert "function startChatWithAgent" in source
    assert "function bindChannelAgent" in source


def test_workspace_scoped_web_services_resolve_selected_agent():
    from conftest import web_backend_py
    source = web_backend_py()
    assert "def _get_workspace_root(session_id: str = None, agent_id: str = None)" in source
    assert "project_store.get_project_dir(session_id, agent_id)" in source
    assert "get_agent_registry().get(agent_id).workspace" in source
    assert "get_conversation_store(_get_workspace_root(agent_id=agent_id))" in source
    assert "_get_workspace_root(agent_id=agent_id)" in source
    assert "get_scheduler_service(agent_id=agent_id)" in source
