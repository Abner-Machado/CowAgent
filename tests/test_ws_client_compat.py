"""websocket_app_run_forever must pass through keepalive knobs on a modern
websocket-client while silently dropping any the installed version is too old to
understand, so a newer keyword (ping_timeout, reconnect) never breaks startup.
"""

import inspect
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.ws_client_compat import websocket_app_run_forever


def _ws_with_signature(*param_names):
    """Build a fake WebSocketApp whose run_forever accepts exactly *param_names*,
    recording the kwargs it was actually called with."""
    recorded = {}

    def run_forever(**kwargs):
        recorded.update(kwargs)

    # Give run_forever a real signature so the compat layer can introspect it.
    params = [
        inspect.Parameter(n, inspect.Parameter.KEYWORD_ONLY, default=None)
        for n in param_names
    ]
    run_forever.__signature__ = inspect.Signature(params)

    ws = MagicMock()
    ws.run_forever = run_forever
    return ws, recorded


class WsClientCompatTest(unittest.TestCase):

    def test_modern_client_receives_all_keepalive_kwargs(self):
        ws, recorded = _ws_with_signature(
            "ping_interval", "ping_timeout", "reconnect"
        )
        websocket_app_run_forever(
            ws, ping_interval=20, ping_timeout=10, reconnect=0
        )
        self.assertEqual(
            recorded, {"ping_interval": 20, "ping_timeout": 10, "reconnect": 0}
        )

    def test_old_client_without_reconnect_drops_only_reconnect(self):
        ws, recorded = _ws_with_signature("ping_interval", "ping_timeout")
        websocket_app_run_forever(
            ws, ping_interval=20, ping_timeout=10, reconnect=0
        )
        self.assertEqual(recorded, {"ping_interval": 20, "ping_timeout": 10})

    def test_very_old_client_drops_unknown_keepalive_kwargs(self):
        ws, recorded = _ws_with_signature("ping_interval")
        websocket_app_run_forever(
            ws, ping_interval=20, ping_timeout=10, reconnect=0
        )
        self.assertEqual(recorded, {"ping_interval": 20})

    def test_var_keyword_signature_keeps_everything(self):
        recorded = {}

        def run_forever(**kwargs):
            recorded.update(kwargs)

        ws = MagicMock()
        ws.run_forever = run_forever  # real **kwargs, no __signature__ override
        websocket_app_run_forever(
            ws, ping_interval=20, ping_timeout=10, reconnect=0
        )
        self.assertEqual(
            recorded, {"ping_interval": 20, "ping_timeout": 10, "reconnect": 0}
        )

    def test_plain_call_without_optional_kwargs_is_untouched(self):
        ws, recorded = _ws_with_signature("ping_interval")
        websocket_app_run_forever(ws)
        self.assertEqual(recorded, {})


if __name__ == "__main__":
    unittest.main()
