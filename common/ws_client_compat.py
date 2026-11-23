import inspect
from typing import Any


def websocket_app_run_forever(ws: Any, **kwargs: Any) -> None:
    """
    Call WebSocketApp.run_forever, dropping any keyword the installed
    websocket-client is too old to understand (e.g. ``reconnect`` was added in a
    later 1.x release). Unknown kwargs are silently stripped so a keepalive knob
    like ``ping_timeout`` never breaks an older client — it simply degrades to
    the client's default behavior.
    """
    # Only bother introspecting when a possibly-unsupported keyword is present;
    # a plain call keeps the common path free of reflection.
    optional_kwargs = ("reconnect", "ping_interval", "ping_timeout")
    if any(k in kwargs for k in optional_kwargs):
        try:
            params = inspect.signature(ws.run_forever).parameters
        except (TypeError, ValueError):
            params = {}
        if params and not any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        ):
            kwargs = {k: v for k, v in kwargs.items() if k in params}
    ws.run_forever(**kwargs)
