from __future__ import annotations

from app.agent.nodes import emit
from app.agent.state import ChatState
from app.core.config import get_settings
from app.db.repositories import MessageRepository, SessionRepository
from app.db.session import get_session_factory
from app.llm.router import get_client_for_role


async def load_context(state: ChatState) -> dict:
    """Load session history + summary; trigger rolling summary past the threshold (§5.3.1/§5.6)."""
    settings = get_settings()
    factory = get_session_factory()
    async with factory() as db:
        messages = await MessageRepository(db).recent_for_context(state["session_id"], limit=24)
        session = await SessionRepository(db).get(state["session_id"], ttl_days=settings.session_ttl_days)
        summary = session.summary if session else None
        message_count = session.message_count if session else len(messages)

    recent = [{"role": m.role, "content": m.content} for m in messages[-12:]]
    summary_failed = False
    if len(messages) > 16:
        older = [{"role": m.role, "content": m.content} for m in messages[:-8]]
        if older:
            try:
                client, model, temperature = get_client_for_role("summary")
                result = await client.complete(
                    role="summary",
                    model=model,
                    temperature=temperature,
                    messages=[{"role": "user", "content": str(older)}],
                    hints={"history": older},
                )
                summary = result.text.strip() or summary
                async with factory() as db:
                    repo = SessionRepository(db)
                    if session is not None:
                        await repo.update_profile(session, summary=summary)
            except Exception as exc:  # noqa: BLE001 - summary failure must not block the answer
                summary_failed = True
                emit({"type": "log", "text": f"summary_failed={type(exc).__name__}, falling back to recent messages"})

    emit(
        {
            "type": "log",
            "text": f"载入 {message_count} 条历史，最近 {len(recent)} 条进入上下文"
            + ("（摘要失败）" if summary_failed else ""),
        }
    )
    return {
        "summary": summary,
        "recent_messages": recent,
        "message_count": message_count,
    }
