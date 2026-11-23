"""Uploads live in the selected Agent's workspace, so the URL handed back to
the browser has to name that Agent.

An <img src> does not pass through the console's fetch wrapper, so nothing
appends agent_id on the way back: whatever /upload returns is fetched verbatim.
When the URL omitted the Agent, /uploads/ resolved against the default Agent's
tmp and every attachment uploaded under a non-default Agent 404'd into a broken
thumbnail. These tests drive a real server because the bug lives in the contract
between the handler that writes the file and the one that reads it back.
"""

import json
import os
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace
from unittest.mock import patch
from wsgiref.simple_server import WSGIRequestHandler, make_server

import pytest

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
DESKTOP_TOKEN = "desktop-token-for-tests"
OTHER_AGENT = "helper"


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def console(tmp_path, monkeypatch):
    """A running console whose Agents own separate workspaces under tmp_path."""
    monkeypatch.setenv("COW_DESKTOP_TOKEN", DESKTOP_TOKEN)

    workspaces = {
        None: tmp_path / "default",
        "default": tmp_path / "default",
        OTHER_AGENT: tmp_path / "agents" / OTHER_AGENT,
    }
    for path in workspaces.values():
        path.mkdir(parents=True, exist_ok=True)

    registry = SimpleNamespace(
        get=lambda agent_id=None: SimpleNamespace(workspace=str(workspaces[agent_id]))
    )

    from channel.web import web_channel

    # A console password set by an earlier test would 401 these requests, and
    # the login flow is not what is under test here.
    with patch("channel.web.api.files._require_auth"), patch(
        "agent.registry.get_agent_registry", return_value=registry
    ):
        app = web_channel.build_app()
        server = make_server("127.0.0.1", 0, app.wsgifunc(), handler_class=_QuietHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield SimpleNamespace(
                base=f"http://127.0.0.1:{server.server_address[1]}",
                workspaces=workspaces,
            )
        finally:
            server.shutdown()
            server.server_close()


def _upload_multipart(console, agent_id):
    """What the browser sends: the Agent rides in the query string only."""
    boundary = "----cowtest"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="photo.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + PNG + f"\r\n--{boundary}--\r\n".encode()

    return _post(
        console,
        agent_id,
        body,
        {"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )


def _upload_local_path(console, agent_id, tmp_path):
    """What the desktop client sends: import by path instead of by bytes."""
    source = tmp_path / "picked.png"
    source.write_bytes(PNG)
    return _post(
        console,
        agent_id,
        json.dumps({"local_path": str(source)}).encode(),
        {
            "Content-Type": "application/json",
            "X-Cow-Desktop-Token": DESKTOP_TOKEN,
        },
    )


def _post(console, agent_id, body, headers):
    query = f"?agent_id={agent_id}" if agent_id else ""
    request = urllib.request.Request(
        f"{console.base}/upload{query}", data=body, headers=headers
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode())
    assert payload["status"] == "success", payload
    return payload


def _fetch(console, url):
    """Fetch a preview URL the way an <img> tag would: exactly as handed over."""
    try:
        with urllib.request.urlopen(f"{console.base}{url}", timeout=20) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, b""


@pytest.mark.parametrize("upload_name", ["multipart", "local_path"])
def test_an_upload_can_be_fetched_back_from_the_url_it_returned(
    console, tmp_path, upload_name
):
    upload = (
        _upload_multipart
        if upload_name == "multipart"
        else lambda c, a: _upload_local_path(c, a, tmp_path)
    )

    for agent_id in (None, OTHER_AGENT):
        result = upload(console, agent_id)
        status, served = _fetch(console, result["preview_url"])

        assert status == 200, (
            f"{upload_name} upload under agent {agent_id!r} returned "
            f"{result['preview_url']}, which 404s — the console renders it as a "
            f"broken thumbnail"
        )
        assert served == PNG


@pytest.mark.parametrize("upload_name", ["multipart", "local_path"])
def test_an_upload_lands_in_the_selected_agents_workspace(
    console, tmp_path, upload_name
):
    upload = (
        _upload_multipart
        if upload_name == "multipart"
        else lambda c, a: _upload_local_path(c, a, tmp_path)
    )

    result = upload(console, OTHER_AGENT)

    expected_dir = console.workspaces[OTHER_AGENT] / "tmp"
    assert os.path.dirname(result["file_path"]) == str(expected_dir), (
        f"{upload_name} upload under agent {OTHER_AGENT!r} was written to "
        f"{result['file_path']}, outside that Agent's workspace"
    )
