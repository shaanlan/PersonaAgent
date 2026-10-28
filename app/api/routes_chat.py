from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import Identity, client_ip, get_identity, resolve_session
from app.api.sse import StreamBroker
from app.core.config import get_settings
from app.core.errors import NotFoundError, PayloadTooLargeError
from app.core.i18n import suggested_questions
from app.core.rate_limit import rate_limiter
from app.db.models import ChatSession
from app.db.session import get_db
from app.schemas.chat import (
    BindResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    FeedbackRequest,
    FeedbackResponse,
    MessageListResponse,
    SessionListResponse,
    StreamMessageRequest,
)
from app.services import chat_service, session_service

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.post("/sessions", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: CreateSessionRequest,
    request: Request,
    identity: Identity = Depends(get_identity),
    db: AsyncSession = Depends(get_db),
) -> CreateSessionResponse:
    settings = get_settings()
    rate_limiter.check(f"session_create:{client_ip(request)}", settings.rate_session_create_per_minute)
    row, token = await session_service.create_session(
        db,
        locale=payload.locale,
        page_context=payload.page_context,
        identity=identity,
        client_ip=client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    return CreateSessionResponse(
        session=session_service.session_out(row),
        session_token=token,
        expires_at=session_service.expires_at(row),
        suggested_questions=suggested_questions(row.locale),
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: AsyncSession = Depends(get_db),
) -> SessionListResponse:
    return await session_service.list_sessions(db, identity, limit=limit, cursor=cursor)


@router.get("/sessions/{session_id}/messages", response_model=MessageListResponse)
async def get_messages(
    session_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    before: str | None = Query(default=None),
    identity: Identity = Depends(get_identity),
    db: AsyncSession = Depends(get_db),
) -> MessageListResponse:
    session = await resolve_session(session_id, identity, db)
    return await session_service.get_messages(db, session, limit=limit, before=before)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    identity: Identity = Depends(get_identity),
    db: AsyncSession = Depends(get_db),
) -> Response:
    session = await resolve_session(session_id, identity, db)
    await session_service.delete_session(db, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/{session_id}:bind", response_model=BindResponse)
async def bind_session(
    session_id: str,
    identity: Identity = Depends(get_identity),
    db: AsyncSession = Depends(get_db),
) -> BindResponse:
    row = await session_service.bind_session(db, session_id, identity)
    return BindResponse(session=session_service.session_out(row), bound=True)


@router.post("/messages/{message_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    message_id: str,
    payload: FeedbackRequest,
    identity: Identity = Depends(get_identity),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    message_repo_session = await _load_session_for_message(message_id, identity, db)
    return await session_service.submit_feedback(
        db,
        message_id=message_id,
        session=message_repo_session,
        identity=identity,
        rating=payload.rating,
        reason=payload.reason,
    )


async def _load_session_for_message(message_id: str, identity: Identity, db: AsyncSession) -> ChatSession:
    from app.db.repositories import MessageRepository

    messages = MessageRepository(db)
    message = await messages.get(message_id)
    if message is None:
        raise NotFoundError("message not found")
    return await resolve_session(message.session_id, identity, db)


@router.post("/sessions/{session_id}/messages:stream")
async def stream_messages(
    session_id: str,
    payload: StreamMessageRequest,
    request: Request,
    identity: Identity = Depends(get_identity),
    db: AsyncSession = Depends(get_db),
) -> EventSourceResponse:
    """Send a message and receive the answer as SSE (design §9.6)."""
    session = await resolve_session(session_id, identity, db)
    ip = client_ip(request)
    slots = chat_service.acquire_stream_slots(identity, ip)
    try:
        state = await chat_service.prepare_turn(
            db,
            session,
            identity,
            payload,
            request_id=getattr(request.state, "request_id", "-"),
            client_ip=ip,
        )
    except Exception:
        chat_service.release_stream_slots(slots)
        raise
    broker = StreamBroker()
    return EventSourceResponse(chat_service.stream_turn(state, broker, slots), ping=15)


@router.post("/sessions/{session_id}/messages/{message_id}:abort", status_code=status.HTTP_204_NO_CONTENT)
async def abort_message(
    session_id: str,
    message_id: str,
    identity: Identity = Depends(get_identity),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stop an in-flight generation; partial content is kept (design §9.8). Idempotent."""
    session = await resolve_session(session_id, identity, db)
    from app.db.repositories import MessageRepository

    message = await MessageRepository(db).get(message_id)
    if message is None or message.session_id != session.id:
        raise NotFoundError("message not found")
    chat_service.abort_stream(message_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _guard_message_length(message: str) -> None:
    settings = get_settings()
    if len(message) > settings.max_user_message_chars:
        raise PayloadTooLargeError(
            f"message exceeds {settings.max_user_message_chars} characters",
            details={"max_chars": settings.max_user_message_chars},
        )
