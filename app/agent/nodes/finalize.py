from __future__ import annotations

from app.agent.actions import valid_url
from app.agent.nodes import emit
from app.agent.state import ChatState
from app.core.config import get_settings
from app.db.repositories import MessageRepository
from app.db.session import get_session_factory


async def finalize(state: ChatState) -> dict:
    """Validate actions/sources, persist the assistant message, close the turn (design §5.3.8)."""
    settings = get_settings()
    actions = [a for a in state.get("actions") or [] if valid_url(str(a.get("url", "")))][:2]
    sources = (state.get("sources") or [])[:3]
    answer = state.get("answer") or (
        "抱歉，我暂时无法回答这个问题。"
        if state.get("locale", "").startswith("zh")
        else "Sorry, I couldn't answer that."
    )
    usage = state.get("usage") or {"input_tokens": 0, "output_tokens": 0}

    message_id = state.get("message_id")
    if message_id:
        factory = get_session_factory()
        async with factory() as db:
            await MessageRepository(db).finalize_assistant(
                message_id,
                content=answer[: settings.max_assistant_chars * 2],
                intent=state.get("intent"),
                intent_confidence=state.get("intent_confidence"),
                slots=state.get("slots"),
                sources=sources,
                actions=actions,
                personal_report_used=bool(state.get("personal_report_used")),
                status="completed",
                model=state.get("model"),
                prompt_version=state.get("prompt_version") or settings.prompt_version,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                latency_ms=state.get("latency_ms"),
                first_token_ms=state.get("first_token_ms"),
            )

    emit(
        {
            "type": "log",
            "text": f"finalize：intent={state.get('intent')} actions={len(actions)} sources={len(sources)} "
            f"report_used={bool(state.get('personal_report_used'))} degraded={bool(state.get('degraded'))}",
        }
    )
    return {
        "actions": actions,
        "sources": sources,
        "answer": answer,
        "finish_reason": state.get("finish_reason") or "stop",
        "usage": usage,
    }
