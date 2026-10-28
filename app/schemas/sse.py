from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.intent import Action, Source


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class MetaEvent(BaseModel):
    request_id: str
    session_id: str
    message_id: str
    model: str | None = None


class SourcesEvent(BaseModel):
    sources: list[Source] = Field(default_factory=list)


class ActionsEvent(BaseModel):
    actions: list[Action] = Field(default_factory=list)


class TokenEvent(BaseModel):
    delta: str


class DoneEvent(BaseModel):
    message_id: str
    finish_reason: Literal["stop", "length", "aborted", "error"] = "stop"
    usage: Usage = Field(default_factory=Usage)


class ErrorEvent(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool = False


class SSEEvent(BaseModel):
    """Envelope used by the broker to encode one SSE frame."""

    event: Literal["meta", "sources", "actions", "token", "done", "error"]
    data: dict[str, Any]

    def encode(self) -> str:
        import json

        payload = json.dumps(self.data, ensure_ascii=False, default=str)
        return f"event: {self.event}\ndata: {payload}\n\n"
