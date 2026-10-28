from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

_END = object()


class StreamBroker:
    """In-memory queue between the graph task and the SSE response (design §5.7)."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._closed = False

    async def emit(self, event: dict[str, Any]) -> None:
        if self._closed:
            return
        await self._queue.put(event)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._queue.put(_END)

    async def iterate(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            item = await self._queue.get()
            if item is _END:
                break
            yield item


def sse_frame(event: dict[str, Any]) -> str:
    """Encode one SSE frame: `event:` + `data:` + blank line (design §9.6)."""
    name = str(event.get("event", "message"))
    payload = json.dumps(event.get("data", {}), ensure_ascii=False, default=str)
    return f"event: {name}\ndata: {payload}\n\n"


def make_event(name: str, **data: Any) -> dict[str, Any]:
    return {"event": name, "data": data}
