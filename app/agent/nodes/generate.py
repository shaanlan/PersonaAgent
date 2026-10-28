from __future__ import annotations

import re
import time

from app.agent.nodes import emit
from app.agent.prompt_loader import LOCALE_NAMES, fill, load_prompt
from app.agent.state import ChatState
from app.core.config import get_settings
from app.llm.router import get_client_for_role

_EXTERNAL_URL_RE = re.compile(r"https?://\S+")
_HTML_RE = re.compile(r"<[^>]+>")


def _site_context(state: ChatState) -> str:
    parts = []
    for index, chunk in enumerate(state.get("retrieved") or [], start=1):
        parts.append(
            f"[{index}] title: {chunk.get('title')}\n"
            f"url: {chunk.get('url_path')}\n"
            f"section: {chunk.get('section')}\n"
            f"text: {chunk.get('text')}"
        )
    return "\n".join(parts) if parts else "（无）"


def _recent_messages(state: ChatState) -> str:
    lines = [f"{m.get('role')}: {str(m.get('content'))[:200]}" for m in state.get("recent_messages") or []]
    return "\n".join(lines) if lines else "（无）"


def _personal_report(state: ChatState) -> str:
    report = state.get("personal_report")
    if not report:
        return "none"
    return (
        f"result_type={report.get('result_type')}, confidence={report.get('confidence')}, scores={report.get('scores')}"
    )


def build_prompt(state: ChatState) -> tuple[str, str]:
    """Split the answer template into (system, user) messages (design §5.8.2)."""
    template = load_prompt("answer")
    filled = fill(
        template,
        locale_name=LOCALE_NAMES.get(state.get("locale", "zh-CN"), "简体中文"),
        summary=state.get("summary") or "（无）",
        recent_messages=_recent_messages(state),
        site_context=_site_context(state),
        personal_report=_personal_report(state),
        user_message=state.get("user_message", ""),
    )
    marker = "[User question]"
    if marker in filled:
        system, _, user = filled.partition(marker)
        return system.strip(), user.strip().lstrip("\n")
    return filled, state.get("user_message", "")


def post_process(text: str) -> str:
    """Strip external links / HTML / prompt-leak fragments (design §8.5)."""
    text = _EXTERNAL_URL_RE.sub("", text)
    text = _HTML_RE.sub("", text)
    return text.strip()


async def generate(state: ChatState) -> dict:
    """Stream the answer through the LLM client and accumulate usage (design §5.3.6)."""
    settings = get_settings()
    system, user = build_prompt(state)
    client, model, temperature = get_client_for_role("answer")
    hints = {
        "locale": state.get("locale", "zh-CN"),
        "intent": state.get("intent", ""),
        "mbti": (state.get("slots") or {}).get("mbti_type") or (state.get("personal_report") or {}).get("result_type"),
        "retrieved": [{"title": c.get("title"), "text": c.get("text")} for c in (state.get("retrieved") or [])[:2]],
        "report": state.get("personal_report"),
        "clarify": state.get("clarify_question"),
        "sufficient": state.get("retrieval_sufficient", False),
    }
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    started = time.perf_counter()
    first_token_ms: int | None = None
    pieces: list[str] = []
    input_tokens = max(1, (len(system) + len(user)) // 2)
    try:
        async for token in client.stream(
            role="answer",
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=600,
            hints=hints,
        ):
            if first_token_ms is None:
                first_token_ms = int((time.perf_counter() - started) * 1000)
            pieces.append(token)
            emit({"type": "token", "delta": token})
    except Exception as exc:  # noqa: BLE001 - design §5.9 fallback to template answer
        emit({"type": "log", "text": f"answer_stream_failed={type(exc).__name__}，使用降级模板"})
        degraded_answer = _degraded_answer(state)
        for index in range(0, len(degraded_answer), 4):
            if first_token_ms is None:
                first_token_ms = int((time.perf_counter() - started) * 1000)
            emit({"type": "token", "delta": degraded_answer[index : index + 4]})
            pieces.append(degraded_answer[index : index + 4])
        return {
            "answer": degraded_answer,
            "finish_reason": "stop",
            "model": f"degraded/{model}",
            "first_token_ms": first_token_ms,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "usage": {"input_tokens": input_tokens, "output_tokens": max(1, len(degraded_answer) // 2)},
            "degraded": True,
        }

    answer = post_process("".join(pieces))[: settings.max_assistant_chars * 2]
    return {
        "answer": answer,
        "finish_reason": "stop",
        "model": model,
        "first_token_ms": first_token_ms,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "usage": {"input_tokens": input_tokens, "output_tokens": max(1, len(answer) // 2)},
        "degraded": False,
    }


def _degraded_answer(state: ChatState) -> str:
    if state.get("locale", "zh-CN").startswith("zh"):
        base = "回答服务暂时不可用，以下是可以直接访问的站内入口："
    else:
        base = "The answer service is temporarily unavailable. Here are on-site entry points instead:"
    clarify = state.get("clarify_question")
    return f"{base}\n\n{clarify or ''}".strip()
