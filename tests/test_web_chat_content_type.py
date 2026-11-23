"""The /chat page must declare its Content-Type.

Browsers sniffed the HTML when the header was missing, so direct access looked
fine and the bug stayed invisible until the console sat behind a reverse proxy
that sends `X-Content-Type-Options: nosniff` — the usual HTTPS setup. With
sniffing disabled and no declared type, the page renders as plain text source
instead of the console.

Every other HTML handler already sets the header; /chat was the only one that
did not, so this guards the one endpoint that regressed.
"""

import os
import sys
import types
import unittest
from unittest.mock import mock_open, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

if "web" not in sys.modules:
    web_stub = types.ModuleType("web")
    web_stub.HTTPError = type("HTTPError", (Exception,), {})
    web_stub.cookies = lambda: {}
    web_stub.header = lambda *args, **kwargs: None
    web_stub.data = lambda: b"{}"
    web_stub.input = lambda **kwargs: types.SimpleNamespace(**kwargs)
    web_stub.setcookie = lambda *args, **kwargs: None
    web_stub.seeother = lambda *args, **kwargs: Exception("seeother")
    web_stub.notfound = lambda *args, **kwargs: Exception("notfound")
    web_stub.badrequest = lambda *args, **kwargs: Exception("badrequest")
    web_stub.application = lambda *args, **kwargs: types.SimpleNamespace(wsgifunc=lambda: None)
    web_stub.httpserver = types.SimpleNamespace(
        LogMiddleware=type("LogMiddleware", (), {"log": lambda *args, **kwargs: None}),
        StaticMiddleware=lambda app: app,
        WSGIServer=lambda *args, **kwargs: types.SimpleNamespace(serve_forever=lambda: None),
    )
    sys.modules["web"] = web_stub


def _capture_headers():
    """Record every web.header call a handler makes outside a request.

    The stub above is skipped when the real web.py is already imported, which
    depends on what else ran first. Patching the name the handler resolves
    keeps these cases independent of that.
    """
    import channel.web.api.pages as pages_api

    sent = []

    def _header(name, value=None):
        sent.append((name, value))

    return patch.object(pages_api.web, "header", _header), sent


class TestChatHandlerContentType(unittest.TestCase):

    def test_chat_page_declares_html_content_type(self):
        """A nosniff proxy cannot sniff, so the type has to be explicit."""
        from channel.web.api.pages import ChatHandler

        patcher, sent = _capture_headers()
        with patcher:
            # No auth to stub out: the shell page is public, the API routes
            # behind it are what _require_auth guards.
            with patch("builtins.open", mock_open(read_data="<!doctype html><html></html>")):
                ChatHandler().GET()

        content_types = [value for name, value in sent if name.lower() == "content-type"]
        self.assertTrue(
            content_types,
            "ChatHandler.GET sent no Content-Type; behind a nosniff proxy the "
            "page renders as plain text source",
        )
        self.assertIn("text/html", content_types[0])
        # The console is UTF-8; without the charset the browser guesses and
        # non-ASCII UI copy mojibakes.
        self.assertIn("charset=utf-8", content_types[0].lower())


if __name__ == "__main__":
    unittest.main()
