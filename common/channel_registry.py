"""Process-wide handle to the running ChannelManager.

The entry module is launched as ``python app.py``, so it lives in
``sys.modules['__main__']``. Any later ``import app`` then builds a *second*,
distinct module object whose module-level globals (including ``_channel_mgr``)
are separate from the ones ``run()`` populated. Code that reached for the live
manager via ``from app import get_channel_manager`` therefore saw ``None`` and
silently fell back to a bare, never-started channel singleton — the scheduler
delivery bug behind issue #3120.

Holding the manager here instead keeps a single shared cell: ``common`` is
always imported as ``common.channel_registry`` (never as ``__main__``), so every
caller — the entry module and the scheduler alike — reads and writes the same
value.
"""

_channel_manager = None


def set_channel_manager(manager) -> None:
    global _channel_manager
    _channel_manager = manager


def get_channel_manager():
    return _channel_manager
