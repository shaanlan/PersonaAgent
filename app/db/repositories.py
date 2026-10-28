from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import ulid
from app.db.models import ChatFeedback, ChatMessage, ChatSession, utcnow


def encode_cursor(updated_at: datetime, row_id: str) -> str:
    raw = f"{updated_at.isoformat()}|{row_id}".encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_cursor(cursor: str) -> tuple[datetime, str] | None:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded).decode()
        iso, row_id = raw.rsplit("|", 1)
        return datetime.fromisoformat(iso), row_id
    except Exception:
        return None


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        locale: str,
        session_token_hash: str,
        uid: int | None = None,
        page_context: dict[str, Any] | None = None,
        user_agent_hash: str | None = None,
        ip_hash: str | None = None,
    ) -> ChatSession:
        row = ChatSession(
            id=ulid(),
            uid=uid,
            session_token_hash=session_token_hash,
            locale=locale,
            page_context_json=page_context,
            user_agent_hash=user_agent_hash,
            ip_hash=ip_hash,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def get(self, session_id: str, *, for_update: bool = False, ttl_days: int = 30) -> ChatSession | None:
        cutoff = utcnow() - timedelta(days=ttl_days)
        stmt = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.status == "active",
            ChatSession.deleted_at.is_(None),
            ChatSession.updated_at >= cutoff,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_uid(
        self, uid: int, *, limit: int = 20, cursor: str | None = None, ttl_days: int = 30
    ) -> list[ChatSession]:
        cutoff = utcnow() - timedelta(days=ttl_days)
        conditions = [
            ChatSession.uid == uid,
            ChatSession.status == "active",
            ChatSession.deleted_at.is_(None),
            ChatSession.updated_at >= cutoff,
        ]
        parsed = decode_cursor(cursor) if cursor else None
        if parsed:
            c_at, c_id = parsed
            conditions.append(
                or_(ChatSession.updated_at < c_at, and_(ChatSession.updated_at == c_at, ChatSession.id < c_id))
            )
        stmt = (
            select(ChatSession)
            .where(*conditions)
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_token(
        self, token_hash: str, *, limit: int = 20, cursor: str | None = None, ttl_days: int = 30
    ) -> list[ChatSession]:
        cutoff = utcnow() - timedelta(days=ttl_days)
        conditions = [
            ChatSession.session_token_hash == token_hash,
            ChatSession.status == "active",
            ChatSession.deleted_at.is_(None),
            ChatSession.updated_at >= cutoff,
        ]
        parsed = decode_cursor(cursor) if cursor else None
        if parsed:
            c_at, c_id = parsed
            conditions.append(
                or_(ChatSession.updated_at < c_at, and_(ChatSession.updated_at == c_at, ChatSession.id < c_id))
            )
        stmt = (
            select(ChatSession)
            .where(*conditions)
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def touch(self, session: ChatSession) -> None:
        session.updated_at = utcnow()
        await self.db.commit()

    async def update_profile(
        self,
        session: ChatSession,
        *,
        title: str | None = None,
        preview: str | None = None,
        message_count: int | None = None,
        last_message_at: datetime | None = None,
        summary: str | None = None,
        summary_updated_at: datetime | None = None,
    ) -> ChatSession:
        if title is not None:
            session.title = title[:100]
        if preview is not None:
            session.last_message_preview = preview[:200]
        if message_count is not None:
            session.message_count = message_count
        if last_message_at is not None:
            session.last_message_at = last_message_at
        if summary is not None:
            session.summary = summary
            session.summary_updated_at = summary_updated_at or utcnow()
        session.updated_at = utcnow()
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def soft_delete(self, session: ChatSession) -> None:
        session.status = "deleted"
        session.deleted_at = utcnow()
        session.updated_at = utcnow()
        await self.db.commit()

    async def bind_uid(self, session_id: str, uid: int, *, ttl_days: int = 30) -> ChatSession | None:
        """Bind an anonymous session to a uid. Returns None if not found/expired.

        Raises app.core.errors.ConflictError when already bound to another uid.
        """
        from app.core.errors import ConflictError

        cutoff = utcnow() - timedelta(days=ttl_days)
        stmt = (
            select(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.status == "active",
                ChatSession.deleted_at.is_(None),
                ChatSession.updated_at >= cutoff,
            )
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        if row.uid is not None and row.uid != uid:
            raise ConflictError("session already bound to another account")
        row.uid = uid
        row.updated_at = utcnow()
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def count_for_uid(self, uid: int, *, ttl_days: int = 30) -> int:
        cutoff = utcnow() - timedelta(days=ttl_days)
        stmt = (
            select(func.count())
            .select_from(ChatSession)
            .where(
                ChatSession.uid == uid,
                ChatSession.status == "active",
                ChatSession.deleted_at.is_(None),
                ChatSession.updated_at >= cutoff,
            )
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_for_token(self, token_hash: str, *, ttl_days: int = 30) -> int:
        cutoff = utcnow() - timedelta(days=ttl_days)
        stmt = (
            select(func.count())
            .select_from(ChatSession)
            .where(
                ChatSession.session_token_hash == token_hash,
                ChatSession.status == "active",
                ChatSession.deleted_at.is_(None),
                ChatSession.updated_at >= cutoff,
            )
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)


class MessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        session_id: str,
        role: str,
        content: str = "",
        client_message_id: str | None = None,
        status: str = "completed",
        model: str | None = None,
        prompt_version: str | None = None,
    ) -> ChatMessage:
        row = ChatMessage(
            id=ulid(),
            session_id=session_id,
            role=role,
            content=content,
            client_message_id=client_message_id,
            status=status,
            model=model,
            prompt_version=prompt_version,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def get(self, message_id: str) -> ChatMessage | None:
        result = await self.db.execute(select(ChatMessage).where(ChatMessage.id == message_id))
        return result.scalar_one_or_none()

    async def find_by_client_id(self, session_id: str, client_message_id: str) -> ChatMessage | None:
        stmt = select(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.client_message_id == client_message_id,
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def list_by_session(
        self, session_id: str, *, limit: int = 50, before: str | None = None
    ) -> list[ChatMessage]:
        conditions = [ChatMessage.session_id == session_id]
        if before:
            anchor = await self.get(before)
            if anchor is not None:
                conditions.append(
                    or_(
                        ChatMessage.created_at > anchor.created_at,
                        and_(ChatMessage.created_at == anchor.created_at, ChatMessage.id > anchor.id),
                    )
                )
        stmt = (
            select(ChatMessage)
            .where(*conditions)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_by_session(self, session_id: str) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == session_id)
        )
        return int(result.scalar_one() or 0)

    async def finalize_assistant(
        self,
        message_id: str,
        *,
        content: str,
        intent: str | None = None,
        intent_confidence: float | None = None,
        slots: dict[str, Any] | None = None,
        sources: list[Any] | None = None,
        actions: list[Any] | None = None,
        personal_report_used: bool = False,
        status: str = "completed",
        error_code: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        latency_ms: int | None = None,
        first_token_ms: int | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "content": content,
            "intent": intent,
            "intent_confidence": intent_confidence,
            "slots_json": slots,
            "sources_json": sources,
            "actions_json": actions,
            "personal_report_used": personal_report_used,
            "status": status,
            "error_code": error_code,
            "model": model,
            "prompt_version": prompt_version,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "first_token_ms": first_token_ms,
            "updated_at": utcnow(),
        }
        await self.db.execute(update(ChatMessage).where(ChatMessage.id == message_id).values(**values))
        await self.db.commit()

    async def recent_for_context(self, session_id: str, *, limit: int = 12) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id, ChatMessage.status != "error")
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(reversed(result.scalars().all()))


class FeedbackRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def upsert(
        self, *, message_id: str, session_id: str, uid: int | None, rating: str, reason: str | None
    ) -> ChatFeedback:
        result = await self.db.execute(select(ChatFeedback).where(ChatFeedback.message_id == message_id))
        row = result.scalar_one_or_none()
        if row is None:
            row = ChatFeedback(
                id=ulid(),
                message_id=message_id,
                session_id=session_id,
                uid=uid,
                rating=rating,
                reason=reason,
            )
            self.db.add(row)
        else:
            row.rating = rating
            row.reason = reason
            row.updated_at = utcnow()
        await self.db.commit()
        await self.db.refresh(row)
        return row
