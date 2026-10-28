from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import get_settings
from app.core.errors import UnavailableError, UpstreamTimeoutError
from app.core.logging import get_logger
from app.llm.client import LLMResult

try:
    import litellm

    litellm.suppress_debug_info = True
    LITELLM_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the [llm] extra
    litellm = None  # type: ignore[assignment]
    LITELLM_AVAILABLE = False

log = get_logger("llm")


class LiteLLMClient:
    """LiteLLM SDK adapter (design §3.2/§8.3) with retry and optional fallback."""

    provider = "litellm"

    def _require(self) -> None:
        if not LITELLM_AVAILABLE:
            raise UnavailableError(
                "litellm is not installed; install with: uv sync --extra llm, or set LLM_PROVIDER=mock"
            )

    def _kwargs(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        api_base: str,
        api_key: str,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": get_settings().llm_timeout_seconds,
        }
        if api_base:
            kwargs["api_base"] = api_base
        if api_key:
            kwargs["api_key"] = api_key
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return kwargs

    async def complete(
        self,
        *,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 300,
        hints: dict[str, Any] | None = None,
    ) -> LLMResult:
        self._require()
        settings = get_settings()
        last_error: Exception | None = None
        attempts: list[tuple[str, str, str]] = [(model, settings.llm_api_base, settings.llm_api_key)]
        if settings.llm_fallback_enabled and settings.llm_fallback_model:
            attempts.append(
                (settings.llm_fallback_model, settings.llm_fallback_api_base, settings.llm_fallback_api_key)
            )

        for attempt_model, api_base, api_key in attempts:
            for retry in range(2):
                try:
                    kwargs = self._kwargs(
                        model=attempt_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        json_mode=(role == "router"),
                        api_base=api_base,
                        api_key=api_key,
                    )
                    response = await litellm.acompletion(**kwargs)  # type: ignore[union-attr]
                    choice = response.choices[0]
                    text = choice.message.content or ""
                    usage = getattr(response, "usage", None)
                    return LLMResult(
                        text=text,
                        model=attempt_model,
                        input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                        output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                        finish_reason=str(getattr(choice, "finish_reason", "stop") or "stop"),
                    )
                except Exception as exc:  # noqa: BLE001 - provider errors vary widely
                    last_error = exc
                    log.warning("llm_call_failed", model=attempt_model, retry=retry, error=type(exc).__name__)
                    if _is_timeout(exc):
                        break
                    await _backoff(retry)
        if last_error is not None and _is_timeout(last_error):
            raise UpstreamTimeoutError("model response timed out") from last_error
        raise UnavailableError("model unavailable after retries") from last_error

    async def stream(
        self,
        *,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 600,
        hints: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        self._require()
        settings = get_settings()
        kwargs = self._kwargs(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,
            api_base=settings.llm_api_base,
            api_key=settings.llm_api_key,
        )
        kwargs["stream"] = True
        try:
            stream = await litellm.acompletion(**kwargs)  # type: ignore[union-attr]
            async for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                content = getattr(delta, "content", None) if delta is not None else None
                if content:
                    yield content
        except TimeoutError as exc:
            raise UpstreamTimeoutError("model stream timed out") from exc
        except Exception as exc:  # noqa: BLE001
            if _is_timeout(exc):
                raise UpstreamTimeoutError("model stream timed out") from exc
            raise UnavailableError("model stream failed") from exc


def _is_timeout(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    return "timeout" in name or "timed out" in str(exc).lower()


async def _backoff(retry: int) -> None:
    import asyncio

    await asyncio.sleep(0.5 * (2**retry))


def parse_router_json(text: str) -> dict[str, Any]:
    """Parse router JSON output with light repair (design §5.9)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError("router output is not valid JSON")
