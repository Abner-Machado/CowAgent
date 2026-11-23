"""The console must resolve the live ChannelManager for newly added channels.

`app.py` is launched as ``python app.py``, so it lives in ``sys.modules['__main__']``.
The web console looked the manager up with ``getattr(sys.modules['__main__'],
'_channel_mgr', None)`` — but the manager is published through
``common.channel_registry`` (see ``common/channel_registry.py``, issue #3120), so
that lookup was always ``None``.

The visible symptom: adding a channel from the console (e.g. a QQ bot with a
valid AppID/AppSecret) appeared to save, then logged

    [WebChannel] ChannelManager not available, cannot start 'qq'

and the channel was never started — the platform reported the bot as
disconnected. These tests pin the resolution so the console keeps working
regardless of how the entry module is named.
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import channel_registry
from channel.web.api import channels as channels_api
from channel.web.core._common import _live_channel_manager


class FakeManager:
    def __init__(self):
        self.channels = {"weixin": object()}
        self.started = []

    def get_channel(self, name):
        return self.channels.get(name)

    def start(self, names, first_start=False):
        self.started.append((list(names), first_start))


class ConsoleChannelManagerResolutionTest(unittest.TestCase):

    def setUp(self):
        self._saved = channel_registry.get_channel_manager()
        self.addCleanup(channel_registry.set_channel_manager, self._saved)
        channel_registry.set_channel_manager(None)

        # Mimic ``python app.py``: __main__ is the entry module. It never
        # carried a ``_channel_mgr`` global; the registry is the shared cell.
        self._saved_main = sys.modules.get("__main__")
        fake_main = types.ModuleType("__main__")
        self.addCleanup(self._restore_main)
        sys.modules["__main__"] = fake_main

    def _restore_main(self):
        if self._saved_main is not None:
            sys.modules["__main__"] = self._saved_main

    def test_helper_returns_manager_published_via_registry(self):
        mgr = FakeManager()
        channel_registry.set_channel_manager(mgr)

        self.assertIs(_live_channel_manager(), mgr)

    def test_helper_returns_none_before_the_app_is_up(self):
        self.assertIsNone(_live_channel_manager())

    def test_handler_resolves_manager_through_registry(self):
        """The regression: __main__ has no _channel_mgr, the registry does."""
        mgr = FakeManager()
        channel_registry.set_channel_manager(mgr)

        self.assertFalse(hasattr(sys.modules["__main__"], "_channel_mgr"))
        self.assertIs(channels_api.ChannelsHandler._channel_mgr(), mgr)

    def test_weixin_login_status_reads_the_live_manager(self):
        class Channel:
            login_status = "confirmed"

        mgr = FakeManager()
        mgr.channels["weixin"] = Channel()
        channel_registry.set_channel_manager(mgr)

        status = channels_api.ChannelsHandler._get_weixin_login_status()
        self.assertIn("confirmed", status)

    def test_source_does_not_read_channel_mgr_off_app_module(self):
        """Guard against reintroducing the looked-up-nowhere global."""
        from conftest import web_backend_py

        source = web_backend_py()
        self.assertNotIn("'_channel_mgr'", source)
        self.assertNotIn('"_channel_mgr"', source)


if __name__ == "__main__":
    unittest.main()
