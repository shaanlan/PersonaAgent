from __future__ import annotations

from app.agent.nodes import emit
from app.agent.state import ChatState
from app.agent.tools.lookup_page import lookup_page
from app.agent.tools.search_content import RetrievalError, chunks_as_dicts, search_content
from app.rag.retriever import build_sources
from app.rag.store import Chunk


async def retrieve(state: ChatState) -> dict:
    """Vector/keyword retrieval + catalog exact hit + sources (design §5.3.4/§7.6)."""
    attempts = state.get("retrieval_attempts", 0) + 1
    locale = state.get("locale", "zh-CN")
    intent = state.get("intent", "")
    query = state.get("search_query") or state.get("user_message", "")
    slots = state.get("slots") or {}

    chunks: list[Chunk] = []
    error: str | None = None
    try:
        chunks = await search_content(query, locale, intent=intent or None)
    except RetrievalError as exc:
        error = type(exc).__name__
        emit({"type": "log", "text": f"检索失败（{error}），降级为 catalog/通用回答"})

    catalog_hit = False
    mbti = slots.get("mbti_type")
    if mbti and intent in {"type_explore", "self_assess", "personal_report"}:
        page = lookup_page("type_detail", locale, mbti_type=mbti)
        if page is not None:
            catalog_hit = True
            if not any(c.url_path == page.url for c in chunks):
                chunks.insert(
                    0,
                    Chunk(
                        chunk_id=f"catalog:{page.url}",
                        doc_id=page.url,
                        locale=page.locale,
                        source_type="type",
                        page_type=page.page_type,
                        title=page.title,
                        section="catalog",
                        url_path=page.url,
                        text=page.summary or page.title,
                        mbti_type=page.mbti_type,
                        slug=page.slug,
                        score=0.9,
                    ),
                )
            else:
                for chunk in chunks:
                    if chunk.url_path == page.url:
                        chunk.score = max(chunk.score, 0.9)

    sufficient = bool(chunks) or catalog_hit
    sources = build_sources(chunks)
    emit(
        {
            "type": "log",
            "text": f"召回 {len(chunks)} 条（catalog_hit={catalog_hit}），充分性={sufficient}，尝试={attempts}"
            + (f"，error={error}" if error else ""),
        }
    )
    return {
        "retrieved": chunks_as_dicts(chunks),
        "sources": [s.model_dump() for s in sources],
        "retrieval_sufficient": sufficient,
        "retrieval_attempts": attempts,
    }
