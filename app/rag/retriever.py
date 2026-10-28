from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.core.config import get_settings
from app.core.i18n import normalize_locale
from app.rag.embeddings import get_embedding_provider
from app.rag.store import Chunk, get_vector_store
from app.schemas.intent import Source

_INTENT_SOURCE_TYPES: dict[str, list[str]] = {
    "type_explore": ["type"],
    "self_assess": ["test_meta", "type"],
    "assess_other": ["blog", "test_meta"],
    "relationship_match": ["relationship", "test_meta"],
    "career_fit": ["career"],
    "relationship_content": ["relationship"],
    "mbti_concept": ["blog"],
    "personal_report": ["career", "site_help"],
    "site_usage": ["site_help"],
}


def keyword_score(chunk: Chunk, query: str, intent: str | None, locale: str) -> float:
    """Rule-side scoring mirroring design §7.6 (works without semantic embeddings)."""
    q = query.lower()
    score = 0.0
    for keyword in chunk.keywords:
        kw = keyword.lower()
        if kw in q:
            score += 0.16
        elif len(kw) >= 3 and any(kw[i : i + 2] in q for i in range(len(kw) - 1)):
            # partial credit for near-miss phrasings ("适合做什么" vs "适合什么工作")
            score += 0.08
    if chunk.mbti_type and chunk.mbti_type.lower() in q:
        score += 0.45
    if chunk.title.lower() in q:
        score += 0.3
    if intent and intent in _INTENT_SOURCE_TYPES and chunk.source_type in _INTENT_SOURCE_TYPES[intent]:
        score += 0.16
    if chunk.locale == normalize_locale(locale):
        score += 0.03
    return round(min(score, 0.99), 3)


def rerank_bonus(chunk: Chunk, query: str, locale: str) -> float:
    """Light re-ranking per design §7.6.4."""
    bonus = 0.0
    q = query.lower()
    if chunk.title.lower() in q or chunk.section.lower() in q:
        bonus += 0.05
    if chunk.locale == normalize_locale(locale):
        bonus += 0.03
    if len(chunk.text) < 40:
        bonus -= 0.1
    return bonus


async def search_content(
    query: str,
    locale: str,
    *,
    top_k: int | None = None,
    source_types: list[str] | None = None,
    score_threshold: float | None = None,
    intent: str | None = None,
) -> list[Chunk]:
    """Retrieve chunks (design §7.6). Mock embedding uses keyword recall so results stay
    deterministic; real embeddings use vector recall + keyword re-rank.
    """
    settings = get_settings()
    top_k = top_k or settings.rag_top_k
    threshold = settings.rag_score_threshold if score_threshold is None else score_threshold
    provider = get_embedding_provider()
    store = get_vector_store()

    if provider.name == "mock":
        candidates = await store.scan(locale=locale, source_types=source_types)
        if not candidates:
            candidates = await store.scan(locale=None, source_types=source_types)
        scored = [(chunk, keyword_score(chunk, query, intent, locale)) for chunk in candidates]
    else:
        vector = (await provider.embed([query]))[0]
        hits = await store.query(vector, settings.rag_candidate_k, locale=locale, source_types=source_types)
        if not hits:
            hits = await store.query(vector, settings.rag_candidate_k, locale=None, source_types=source_types)
        scored = [
            (
                chunk,
                min(
                    0.99,
                    0.55 * score
                    + 0.45 * keyword_score(chunk, query, intent, locale)
                    + rerank_bonus(chunk, query, locale),
                ),
            )
            for chunk, score in hits
        ]

    scored = [(chunk, score) for chunk, score in scored if score >= threshold]
    scored.sort(key=lambda item: -item[1])

    per_doc: dict[str, int] = {}
    results: list[Chunk] = []
    for chunk, score in scored:
        if per_doc.get(chunk.doc_id, 0) >= settings.rag_max_per_doc:
            continue
        per_doc[chunk.doc_id] = per_doc.get(chunk.doc_id, 0) + 1
        results.append(replace(chunk, score=score))
        if len(results) >= top_k:
            break
    return results


def build_sources(chunks: list[Chunk], max_sources: int | None = None) -> list[Source]:
    settings = get_settings()
    limit = max_sources or settings.rag_max_sources
    sources: list[Source] = []
    seen: set[str] = set()
    for index, chunk in enumerate(chunks, start=1):
        if chunk.url_path in seen:
            continue
        seen.add(chunk.url_path)
        sources.append(
            Source(
                id=f"src_{index}",
                title=chunk.title,
                section=chunk.section.split(" > ")[-1] if chunk.section else None,
                url=chunk.url_path,
                source_type=chunk.source_type,
                score=round(chunk.score, 3),
            )
        )
        if len(sources) >= limit:
            break
    return sources


def chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "title": chunk.title,
        "section": chunk.section,
        "url_path": chunk.url_path,
        "source_type": chunk.source_type,
        "page_type": chunk.page_type,
        "locale": chunk.locale,
        "mbti_type": chunk.mbti_type,
        "text": chunk.text,
        "score": chunk.score,
    }
