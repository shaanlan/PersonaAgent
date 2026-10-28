from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Identity, ip_hash, user_agent_hash
from app.core.config import get_settings
from app.core.errors import NotFoundError, UnauthorizedError, ValidationError
from app.core.i18n import normalize_locale
from app.core.security import generate_session_token, hash_session_token
from app.db.models import ChatMessage, ChatSession, utcnow
from app.db.repositories import FeedbackRepository, MessageRepository, SessionRepository, encode_cursor
from app.schemas.chat import (
    FeedbackResponse,
    MessageListResponse,
    MessageOut,
    PageContext,
    SessionBrief,
    SessionListResponse,
    SessionOut,
)


def session_out(row: ChatSession) -> SessionOut:
    return SessionOut(
        id=row.id,
        title=row.title,
        locale=row.locale,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_message_preview=row.last_message_preview,
        message_count=row.message_count,
    )


def message_out(row: ChatMessage) -> MessageOut:
    return MessageOut(
        id=row.id,
        role=row.role,
        content=row.content,
        created_at=row.created_at,
        client_message_id=row.client_message_id,
        intent=row.intent,
        sources=row.sources_json,
        actions=row.actions_json,
        status=row.status,
    )


async def create_session(
    db: AsyncSession,
    *,
    locale: str,
    page_context: PageContext | None,
    identity: Identity,
    client_ip: str,
    user_agent: str | None,
) -> tuple[ChatSession, str]:
    settings = get_settings()
    repo = SessionRepository(db)
    if identity.uid is not None:
        count = await repo.count_for_uid(identity.uid, ttl_days=settings.session_ttl_days)
        if count >= settings.max_sessions_per_user:
            raise ValidationError(f"session limit reached ({settings.max_sessions_per_user})")
    token = generate_session_token()
    row = await repo.create(
        locale=normalize_locale(locale),
        session_token_hash=hash_session_token(token),
        uid=identity.uid,
        page_context=page_context.model_dump(exclude_none=True) if page_context else None,
        user_agent_hash=user_agent_hash(user_agent),
        ip_hash=ip_hash(client_ip),
    )
    return row, token


async def list_sessions(
    db: AsyncSession,
    identity: Identity,
    *,
    limit: int = 20,
    cursor: str | None = None,
) -> SessionListResponse:
    settings = get_settings()
    if not identity.has_credentials:
        raise UnauthorizedError("X-Chat-Session-Token or Authorization required")
    repo = SessionRepository(db)
    limit = max(1, min(limit, 50))
    rows: list[ChatSession] = []
    if identity.uid is not None:
        rows.extend(
            await repo.list_for_uid(identity.uid, limit=limit, cursor=cursor, ttl_days=settings.session_ttl_days)
        )
    if identity.session_token:
        token_rows = await repo.list_for_token(
            identity.session_token_hash or "",
            limit=limit,
            cursor=cursor,
            ttl_days=settings.session_ttl_days,
        )
        seen = {r.id for r in rows}
        rows.extend(r for r in token_rows if r.id not in seen)
    rows.sort(key=lambda r: (r.updated_at, r.id), reverse=True)
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].updated_at, rows[-1].id) if len(rows) == limit else None
    return SessionListResponse(items=[session_out(r) for r in rows], next_cursor=next_cursor)


async def get_messages(
    db: AsyncSession,
    session: ChatSession,
    *,
    limit: int = 50,
    before: str | None = None,
) -> MessageListResponse:
    repo = MessageRepository(db)
    limit = max(1, min(limit, 100))
    rows = await repo.list_by_session(session.id, limit=limit, before=before)
    next_cursor = rows[0].id if len(rows) == limit else None
    return MessageListResponse(
        session=SessionBrief(id=session.id, title=session.title),
        items=[message_out(r) for r in rows],
        next_cursor=next_cursor,
    )


async def delete_session(db: AsyncSession, session: ChatSession) -> None:
    repo = SessionRepository(db)
    await repo.soft_delete(session)


async def bind_session(db: AsyncSession, session_id: str, identity: Identity) -> ChatSession:
    if identity.uid is None:
        raise UnauthorizedError("Authorization required to bind session")
    if not identity.session_token:
        raise NotFoundError("session not found")
    settings = get_settings()
    repo = SessionRepository(db)
    row = await repo.bind_uid(session_id, identity.uid, ttl_days=settings.session_ttl_days)
    if row is None:
        raise NotFoundError("session not found")
    if not _token_matches(row, identity.session_token):
        raise NotFoundError("session not found")
    return row


def _token_matches(session: ChatSession, token: str) -> bool:
    import hmac

    return hmac.compare_digest(hash_session_token(token), session.session_token_hash)


async def submit_feedback(
    db: AsyncSession,
    *,
    message_id: str,
    session: ChatSession,
    identity: Identity,
    rating: str,
    reason: str | None,
) -> FeedbackResponse:
    messages = MessageRepository(db)
    message = await messages.get(message_id)
    if message is None or message.session_id != session.id:
        raise NotFoundError("message not found")
    if message.role != "assistant":
        raise ValidationError("feedback only allowed on assistant messages")
    repo = FeedbackRepository(db)
    row = await repo.upsert(
        message_id=message_id,
        session_id=session.id,
        uid=identity.uid,
        rating=rating,
        reason=reason,
    )
    return FeedbackResponse(id=row.id, message_id=row.message_id, rating=row.rating, reason=row.reason)


def expires_at(row: ChatSession) -> Any:
    return row.updated_at + timedelta(days=get_settings().session_ttl_days)


def initial_title(message: str) -> str:
    compact = " ".join(message.split())[:40]
    return compact or "新对话"


def touch_last_activity(
    repo: SessionRepository,
    session: ChatSession,
    *,
    preview: str,
    message_count: int,
) -> None:
    session.last_message_preview = preview[:200]
    session.message_count = message_count
    session.last_message_at = utcnow()
    session.updated_at = utcnow()


def default_locale() -> str:
    return normalize_locale(None)
