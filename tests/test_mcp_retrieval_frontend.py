"""Frontend contracts for MCP tool retrieval observability."""

from pathlib import Path
from types import SimpleNamespace

from channel.web.web_channel import WebChannel


ROOT = Path(__file__).parents[1]


def test_web_sse_forwards_only_sanitized_retrieval_metadata():
    published = []
    channel = SimpleNamespace(
        sse_streams={"req": object()},
        _publish_sse_event=lambda request_id, item: published.append(
            (request_id, item)
        ),
    )
    callback = WebChannel.__wrapped__._make_sse_callback(channel, "req")

    callback({
        "type": "tool_retrieval",
        "data": {
            "mode": "retrieved",
            "total_mcp_tools": 25,
            "selected_mcp_tools": 2,
            "builtin_tools": 3,
            "top_k": 2,
            "candidate_count": 25,
            "selected_tools": ["search", "read"],
            "ranked_tools": [{"name": "search", "score": 0.98}],
            "fallback_reason": None,
            "query": "must not reach the frontend",
        },
    })

    assert published[0][0] == "req"
    assert published[0][1]["type"] == "tool_retrieval"
    assert published[0][1]["selected_tools"] == ["search", "read"]
    assert "query" not in published[0][1]

    callback({
        "type": "tool_retrieval",
        "data": {
            "mode": "fallback",
            "total_mcp_tools": 25,
            "selected_mcp_tools": 25,
            "fallback_reason": "missing_query_vector",
        },
    })
    assert published[1][1]["mode"] == "fallback"
    assert published[1][1]["fallback_reason"] == "missing_query_vector"


def test_web_and_desktop_render_the_retrieval_event():
    web = (ROOT / "channel/web/static/js/chat/send.js").read_text(encoding="utf-8")
    desktop_store = (
        ROOT / "desktop/src/renderer/src/store/chatStore.ts"
    ).read_text(encoding="utf-8")
    desktop_steps = (
        ROOT / "desktop/src/renderer/src/components/MessageSteps.tsx"
    ).read_text(encoding="utf-8")

    assert "item.type === 'tool_retrieval'" in web
    assert "escapeHtml(selected.join(', '))" in web
    assert "case 'tool_retrieval':" in desktop_store
    assert "step.type === 'retrieval'" in desktop_steps
    assert "retrieval.fallback_reason" in desktop_steps
