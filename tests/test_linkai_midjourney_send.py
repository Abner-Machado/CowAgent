"""Regression tests for the Midjourney plugin's channel-send retry.

``plugins/linkai/midjourney.py::_send`` mirrors ``ChatChannel._send``
(channel/chat_channel.py:437): on a transport failure it retries twice with a
3s/6s backoff. The retry used to call ``channel.send`` with the retry counter
as a third positional argument instead of recursing into ``_send``, so every
real channel -- all of which declare ``send(self, reply, context)``
(channel/channel.py:133) -- raised TypeError instead of retrying.
"""

from unittest.mock import patch

import plugins
from bridge.reply import Reply, ReplyType

plugins.instance.current_plugin_path = "./plugins/linkai"
import plugins.linkai.midjourney as midjourney  # noqa: E402,F401
plugins.instance.current_plugin_path = None


class _Channel:
    """Fails the first ``fail_times`` sends, then accepts."""

    def __init__(self, fail_times, exc=RuntimeError):
        self.fail_times = fail_times
        self.exc = exc
        self.attempts = 0

    def send(self, reply, context):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise self.exc("transport failure")


def _run(fail_times, exc=RuntimeError):
    channel = _Channel(fail_times, exc)
    with patch.object(midjourney, "time") as clock:
        midjourney._send(channel, Reply(ReplyType.INFO, "drawing done"), object())
    return channel, clock


def test_retries_until_the_send_succeeds():
    channel, clock = _run(fail_times=2)
    assert channel.attempts == 3
    assert [c.args[0] for c in clock.sleep.call_args_list] == [3, 6]


def test_gives_up_after_two_retries_without_raising():
    channel, clock = _run(fail_times=99)
    assert channel.attempts == 3
    assert clock.sleep.call_count == 2


def test_not_implemented_error_is_not_retried():
    channel, clock = _run(fail_times=99, exc=NotImplementedError)
    assert channel.attempts == 1
    assert clock.sleep.call_count == 0
