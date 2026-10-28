from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_chat, routes_health
from app.core.config import get_settings
from app.core.errors import install_exception_handlers
from app.core.ids import request_id as new_request_id
from app.core.logging import request_id_var, setup_logging


async def _create_tables_if_needed() -> None:
    from app.core.config import get_settings as _gs

    if not _gs().db_auto_create:
        return
    from app.db import models  # noqa: F401  register mappers
    from app.db.base import Base
    from app.db.session import engine

    assert engine is not None
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    setup_logging(settings.log_level, dev=not settings.is_production)
    from app.db.session import dispose_db, init_db

    init_db()
    await _create_tables_if_needed()
    from app.rag.ingest import ensure_index

    await ensure_index()
    yield
    await dispose_db()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="persona-chat",
        version=settings.app_version,
        description="PersonaAgent chat service: FastAPI + LangGraph controlled MBTI assistant",
        lifespan=lifespan,
    )
    install_exception_handlers(app)
    allow_origins = [] if settings.is_production else ["http://localhost:3000", "http://127.0.0.1:3000"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "X-Chat-Session-Token", "X-Request-Id"],
        expose_headers=["X-Request-Id"],
    )

    @app.middleware("http")
    async def bind_request_id(request: Request, call_next: Callable[..., Any]) -> Any:
        rid = request.headers.get("X-Request-Id") or new_request_id()
        request.state.request_id = rid
        request_id_var.set(rid)
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    app.include_router(routes_health.router)
    app.include_router(routes_chat.router)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.chat_bind_addr, port=settings.app_port, reload=False)


if __name__ == "__main__":
    main()
