from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import GRAPH
from app.agent.state import ChatState
from app.api.deps import Identity
from app.api.sse import StreamBroker, make_event
from app.core.config import get_settings
from app.core.errors import ConflictError, PayloadTooLargeError, RateLimitedError
from app.core.i18n import normalize_locale
from app.core.logging import get_logger
from app.core.rate_limit import rate_limiter, stream_limiter
from app.db.models import ChatSession, utcnow
from app.db.repositories import MessageRepository, SessionRepository
from app.db.session import get_session_factory
from app.schemas.chat import StreamMessageRequest

log = get_logger("chat")

ACTIVE_STREAMS: dict[str, asyncio.Task] = {}


def initial_state(
    *,
    request_id: str,
    session: ChatSession,
    identity: Identity,
    payload: StreamMessageRequest,
    message_id: str,
) -> ChatState:
    settings = get_settings()
    locale = normalize_locale(payload.locale or session.locale)
    page_context: dict[str, Any] | None
    if payload.page_context is not None:
        page_context = payload.page_context.model_dump(exclude_none=True)
    else:
        page_context = session.page_context_json
    return {
        "request_id": request_id,
        "session_id": session.id,
        "message_id": message_id,
        "client_message_id": payload.client_message_id,
        "locale": locale,
        "page_context": page_context,
        "user": {"uid": identity.uid} if identity.uid is not None else None,
        "bearer_token": identity.bearer,
        "summary": None,
        "recent_messages": [],
        "message_count": 0,
        "user_message": payload.message,
        "intent": "",
        "intent_confidence": 0.0,
        "slots": {},
        "search_query": payload.message,
        "need_personal_report": False,
        "clarify_question": None,
        "personal_report": None,
        "personal_report_used": False,
        "retrieval_attempts": 0,
        "retrieved": [],
        "retrieval_sufficient": False,
        "sources": [],
        "actions": [],
        "answer": "",
        "finish_reason": "",
        "usage": {},
        "error": None,
        "model": settings.llm_answer_model if settings.llm_enabled else "mock/template",
        "prompt_version": settings.prompt_version,
        "first_token_ms": None,
        "latency_ms": None,
        "degraded": False,
    }


async def prepare_turn(
    db: AsyncSession,
    session: ChatSession,
    identity: Identity,
    payload: StreamMessageRequest,
    *,
    request_id: str,
    client_ip: str,
) -> ChatState:
    """Guards + message writes that must happen BEFORE the stream starts (design §2.2)."""
    settings = get_settings()
    if len(payload.message) > settings.max_user_message_chars:
        raise PayloadTooLargeError(
            f"message exceeds {settings.max_user_message_chars} characters",
            details={"max_chars": settings.max_user_message_chars},
        )
    rate_limiter.check(f"message:{session.id}", settings.rate_message_per_minute)

    messages = MessageRepository(db)
    if payload.client_message_id:
        existing = await messages.find_by_client_id(session.id, payload.client_message_id)
        if existing is not None:
            raise ConflictError("message with this client_message_id already exists")

    await messages.create(
        session_id=session.id,
        role="user",
        content=payload.message,
        client_message_id=payload.client_message_id,
        status="completed",
    )
    assistant = await messages.create(
        session_id=session.id,
        role="assistant",
        content="",
        status="pending",
        model=settings.llm_answer_model if settings.llm_enabled else "mock/template",
        prompt_version=settings.prompt_version,
    )
    count = await messages.count_by_session(session.id)
    repo = SessionRepository(db)
    await repo.update_profile(
        session,
        title=session.title or _initial_title(payload.message),
        preview=payload.message,
        message_count=count,
        last_message_at=utcnow(),
    )
    return initial_state(
        request_id=request_id,
        session=session,
        identity=identity,
        payload=payload,
        message_id=assistant.id,
    )


def acquire_stream_slots(identity: Identity, client_ip: str) -> list[str]:
    """Concurrency limits (design §12.7). Returns acquired keys; release in the stream finally."""
    settings = get_settings()
    keys: list[tuple[str, int]] = [("stream:global", settings.rate_global_streams)]
    keys.append((f"stream:ip:{client_ip}", settings.rate_ip_streams))
    if identity.uid is not None:
        keys.append((f"stream:uid:{identity.uid}", settings.rate_uid_streams))
    acquired: list[str] = []
    for key, limit in keys:
        if not stream_limiter.try_acquire(key, limit):
            for done in reversed(acquired):
                stream_limiter.release(done)
            raise RateLimitedError("too many concurrent streams", retry_after=5)
        acquired.append(key)
    return acquired


def release_stream_slots(keys: list[str]) -> None:
    for key in reversed(keys):
        stream_limiter.release(key)


async def run_graph(state: ChatState, broker: StreamBroker) -> None:
    """Drive the LangGraph graph and translate its stream into SSE events (design §9.6)."""
    request_id = state.get("request_id", "-")
    message_id = state.get("message_id", "")
    state_view: dict[str, Any] = dict(state)
    pieces: list[str] = []
    flushed = False
    first_token_ms: int | None = None
    started = time.perf_counter()

    try:
        async for mode, chunk in GRAPH.astream(state, stream_mode=["updates", "custom"]):
            if mode == "custom":
                event = chunk if isinstance(chunk, dict) else {}
                kind = event.get("type")
                if kind == "token":
                    if not flushed:
                        await _flush_sources_actions(broker, state_view)
                        flushed = True
                    if first_token_ms is None:
                        first_token_ms = int((time.perf_counter() - started) * 1000)
                    delta = str(event.get("delta", ""))
                    pieces.append(delta)
                    await broker.emit(make_event("token", delta=delta))
                elif kind == "log":
                    log.info(
                        "agent_step",
                        request_id=request_id,
                        session_id=state.get("session_id"),
                        text=event.get("text"),
                    )
            elif mode == "updates":
                if not isinstance(chunk, dict) or "__interrupt__" in chunk:
                    continue
                for key, delta in chunk.items():
                    if key.startswith("__") or not isinstance(delta, dict):
                        continue
                    state_view.update(delta)

        if not flushed:
            await _flush_sources_actions(broker, state_view)
        await broker.emit(
            make_event(
                "done",
                message_id=message_id,
                finish_reason=state_view.get("finish_reason") or "stop",
                usage=state_view.get("usage") or {"input_tokens": 0, "output_tokens": 0},
            )
        )
        log.info(
            "turn_completed",
            request_id=request_id,
            session_id=state.get("session_id"),
            intent=state_view.get("intent"),
            attempts=state_view.get("retrieval_attempts"),
            degraded=bool(state_view.get("degraded")),
            report_used=bool(state_view.get("personal_report_used")),
            first_token_ms=first_token_ms,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
    except asyncio.CancelledError:
        # User pressed stop or the client disconnected: keep partial content (design §9.8).
        await _finalize_partial(state, pieces, status="aborted", first_token_ms=first_token_ms, started=started)
        await broker.emit(
            make_event(
                "done",
                message_id=message_id,
                finish_reason="aborted",
                usage={"input_tokens": 0, "output_tokens": sum(len(p) for p in pieces) // 2},
            )
        )
    except Exception as exc:  # noqa: BLE001 - never leak internals to the client
        log.exception("turn_failed", request_id=request_id, error=type(exc).__name__)
        await _finalize_partial(
            state, pieces, status="error", error_code="INTERNAL", first_token_ms=first_token_ms, started=started
        )
        await broker.emit(
            make_event(
                "error",
                code="UNAVAILABLE",
                message="回答服务暂时不可用，请稍后重试",
                request_id=request_id,
                retryable=True,
            )
        )
    finally:
        await broker.close()


async def _flush_sources_actions(broker: StreamBroker, state_view: dict[str, Any]) -> None:
    await broker.emit(make_event("sources", sources=state_view.get("sources") or []))
    await broker.emit(make_event("actions", actions=state_view.get("actions") or []))


async def _finalize_partial(
    state: ChatState,
    pieces: list[str],
    *,
    status: str,
    error_code: str | None = None,
    first_token_ms: int | None = None,
    started: float | None = None,
) -> None:
    message_id = state.get("message_id")
    if not message_id:
        return
    content = "".join(pieces)
    latency = int((time.perf_counter() - started) * 1000) if started else None
    try:
        factory = get_session_factory()
        async with factory() as db:
            await MessageRepository(db).finalize_assistant(
                message_id,
                content=content,
                status=status,
                error_code=error_code,
                model=state.get("model"),
                prompt_version=state.get("prompt_version"),
                latency_ms=latency,
                first_token_ms=first_token_ms,
                output_tokens=max(1, len(content) // 2) if content else 0,
            )
    except Exception as exc:  # noqa: BLE001 - best effort during teardown
        log.warning("finalize_partial_failed", error=type(exc).__name__, message_id=message_id)


async def stream_turn(
    state: ChatState,
    broker: StreamBroker,
    slots: list[str],
) -> AsyncIterator[dict[str, Any]]:
    """SSE generator: meta first, then graph events, then release concurrency slots."""
    task: asyncio.Task | None = None
    try:
        await broker.emit(
            make_event(
                "meta",
                request_id=state.get("request_id", ""),
                session_id=state.get("session_id", ""),
                message_id=state.get("message_id", ""),
                model=state.get("model"),
            )
        )
        task = asyncio.create_task(run_graph(state, broker))
        ACTIVE_STREAMS[state.get("message_id", "")] = task
        async for event in broker.iterate():
            yield frame(event)
    finally:
        message_id = state.get("message_id", "")
        ACTIVE_STREAMS.pop(message_id, None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        release_stream_slots(slots)


def abort_stream(message_id: str) -> bool:
    """Cancel an in-flight generation (design §9.8). Returns False when nothing is running."""
    task = ACTIVE_STREAMS.get(message_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


def _initial_title(message: str) -> str:
    compact = " ".join(message.split())[:40]
    return compact or "新对话"


def frame(event: dict[str, Any]) -> dict[str, str]:
    """Convert a broker event into an sse-starlette payload."""
    return {
        "event": str(event.get("event", "message")),
        "data": json.dumps(event.get("data", {}), ensure_ascii=False, default=str),
    }
