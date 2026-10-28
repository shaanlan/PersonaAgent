from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Enum, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects import mysql as mysql_dialect
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DateTime3 = DateTime().with_variant(mysql_dialect.DATETIME(fsp=3), "mysql")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = ({"mysql_charset": "utf8mb4", "mysql_engine": "InnoDB"},)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    uid: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=False)
    session_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="zh-CN")
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_updated_at: Mapped[datetime | None] = mapped_column(DateTime3, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime3, nullable=True)
    last_message_preview: Mapped[str | None] = mapped_column(String(200), nullable=True)
    page_context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("active", "deleted", name="chat_session_status"),
        nullable=False,
        default="active",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime3, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime3, nullable=False, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime3, nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "client_message_id", name="uk_messages_session_client"),
        {"mysql_charset": "utf8mb4", "mysql_engine": "InnoDB"},
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    role: Mapped[str] = mapped_column(
        Enum("user", "assistant", "system", name="chat_message_role"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    client_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    intent_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    slots_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sources_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    actions_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    personal_report_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        Enum("pending", "completed", "aborted", "error", name="chat_message_status"),
        nullable=False,
        default="completed",
    )
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_token_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime3, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime3, nullable=False, default=utcnow, onupdate=utcnow)


class ChatFeedback(Base):
    __tablename__ = "chat_feedback"
    __table_args__ = ({"mysql_charset": "utf8mb4", "mysql_engine": "InnoDB"},)

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(26), nullable=False, unique=True)
    session_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)
    uid: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rating: Mapped[str] = mapped_column(
        Enum("helpful", "unhelpful", name="chat_feedback_rating"),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime3, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime3, nullable=False, default=utcnow, onupdate=utcnow)
