from __future__ import annotations

import os
import tempfile

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DB_AUTO_CREATE", "true")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{tempfile.mkdtemp(prefix='persona_test_')}/test.db")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("EMBEDDING_PROVIDER", "mock")
os.environ.setdefault("PERSONALITY_API_BASE_URL", "")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.rate_limit import rate_limiter  # noqa: E402

get_settings.cache_clear()


@pytest_asyncio.fixture
async def app():
    from app.main import app as fastapi_app

    async with fastapi_app.router.lifespan_context(fastapi_app):
        yield fastapi_app


@pytest_asyncio.fixture
async def client(app):
    rate_limiter.reset()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as value:
        yield value


@pytest_asyncio.fixture
async def session_headers(client):
    response = await client.post("/api/v1/chat/sessions", json={"locale": "zh-CN"})
    assert response.status_code == 201, response.text
    body = response.json()
    return body["session"]["id"], {"X-Chat-Session-Token": body["session_token"]}


async def read_sse(client: AsyncClient, url: str, payload: dict, headers: dict) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    async with client.stream("POST", url, json=payload, headers={"Accept": "text/event-stream", **headers}) as response:
        assert response.status_code == 200, await response.aread()
        buffer = ""
        async for chunk in response.aiter_text():
            buffer += chunk.replace("\r\n", "\n")
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                name = None
                data = None
                for line in block.split("\n"):
                    if line.startswith("event: "):
                        name = line[7:]
                    elif line.startswith("data: "):
                        import json as _json

                        data = _json.loads(line[6:])
                if name:
                    events.append((name, data))
                if name in {"done", "error"}:
                    return events
    return events
