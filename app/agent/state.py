from __future__ import annotations

from typing import Any, TypedDict


class ChatState(TypedDict, total=False):
    """LangGraph state (design §5.1). Only serialisable data; no connections/queues."""

    request_id: str
    session_id: str
    message_id: str
    client_message_id: str | None
    locale: str
    page_context: dict[str, Any] | None
    user: dict[str, Any] | None
    bearer_token: str | None

    summary: str | None
    recent_messages: list[dict[str, Any]]
    message_count: int

    user_message: str

    intent: str
    intent_confidence: float
    slots: dict[str, Any]
    search_query: str
    need_personal_report: bool
    clarify_question: str | None

    personal_report: dict[str, Any] | None
    personal_report_used: bool

    retrieval_attempts: int
    retrieved: list[dict[str, Any]]
    retrieval_sufficient: bool
    sources: list[dict[str, Any]]

    actions: list[dict[str, Any]]
    answer: str
    finish_reason: str
    usage: dict[str, Any]
    error: dict[str, Any] | None

    model: str
    prompt_version: str
    first_token_ms: int | None
    latency_ms: int | None
    degraded: bool
