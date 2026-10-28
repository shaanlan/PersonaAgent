from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_session_factory

router = APIRouter(tags=["health"])


async def _check_db() -> str:
    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


def _modes() -> dict[str, str]:
    settings = get_settings()
    return {
        "db": "mysql" if settings.mysql_host or settings.database_url.startswith("mysql") else "sqlite",
        "chroma": "mock",
        "llm": settings.llm_provider if settings.llm_enabled else "mock",
        "embedding": settings.embedding_provider if settings.embedding_enabled else "mock",
    }


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> JSONResponse:
    settings = get_settings()
    checks = {
        "db": await _check_db(),
        "chroma": "ok",
        "llm": "ok",
        "embedding": "ok",
    }
    ready = all(value == "ok" for value in checks.values())
    payload = {
        "status": "ok" if ready else "degraded",
        "checks": checks,
        "modes": _modes(),
        "version": settings.app_version,
        "snapshot_id": settings.index_snapshot_id,
    }
    return JSONResponse(content=payload, status_code=200 if ready else 503)
