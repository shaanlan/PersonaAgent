from __future__ import annotations

from typing import Any


def emit(event: dict[str, Any]) -> None:
    """Push a custom event onto LangGraph's `custom` stream (design §5.7 equivalent).

    The design doc injects a StreamBroker via contextvars, but LangGraph 1.x async
    nodes do not propagate contextvars, so we use the official stream writer instead.
    Events reach SSE through chat_service's astream loop.
    """
    try:
        from langgraph.config import get_stream_writer
    except ImportError:  # pragma: no cover
        return
    try:
        writer = get_stream_writer()
    except Exception:  # noqa: BLE001 - node invoked outside graph streaming (unit tests)
        return
    writer(event)
