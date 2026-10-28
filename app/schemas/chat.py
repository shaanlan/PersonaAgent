from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.intent import Action, Source


class PageContext(BaseModel):
    path: str
    page_type: str | None = None
    slug: str | None = None
    mbti_type: str | None = None


class CreateSessionRequest(BaseModel):
    locale: str = Field(default="zh-CN", max_length=10)
    page_context: PageContext | None = None


class SessionOut(BaseModel):
    id: str
    title: str | None = None
    locale: str
    created_at: datetime
    updated_at: datetime
    last_message_preview: str | None = None
    message_count: int = 0


class CreateSessionResponse(BaseModel):
    session: SessionOut
    session_token: str
    expires_at: datetime
    suggested_questions: list[str]


class SessionListResponse(BaseModel):
    items: list[SessionOut]
    next_cursor: str | None = None


class SessionBrief(BaseModel):
    id: str
    title: str | None = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    client_message_id: str | None = None
    intent: str | None = None
    sources: list[Source] | None = None
    actions: list[Action] | None = None
    status: str | None = None


class MessageListResponse(BaseModel):
    session: SessionBrief
    items: list[MessageOut]
    next_cursor: str | None = None


class StreamOptions(BaseModel):
    include_personal_report: bool = False


class StreamMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    client_message_id: str | None = Field(default=None, max_length=64)
    locale: str | None = Field(default=None, max_length=10)
    page_context: PageContext | None = None
    options: StreamOptions | None = None


class FeedbackRequest(BaseModel):
    rating: Literal["helpful", "unhelpful"]
    reason: Literal["inaccurate", "irrelevant", "too_generic", "bad_link", "other"] | None = None


class FeedbackResponse(BaseModel):
    id: str
    message_id: str
    rating: str
    reason: str | None = None


class BindResponse(BaseModel):
    session: SessionOut
    bound: bool


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    error: ErrorBody
