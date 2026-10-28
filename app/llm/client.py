from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.config import get_settings


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"


class LLMClient(Protocol):
    provider: str

    async def complete(
        self,
        *,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 300,
        hints: dict[str, Any] | None = None,
    ) -> LLMResult: ...

    def stream(
        self,
        *,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 600,
        hints: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]: ...


def get_llm_client() -> LLMClient:
    settings = get_settings()
    if settings.llm_enabled:
        from app.llm.litellm_client import LiteLLMClient

        return LiteLLMClient()
    from app.llm.mock import MockLLMClient

    return MockLLMClient()
