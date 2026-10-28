from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.rag.retriever import search_content as _search
from app.rag.store import Chunk

log = get_logger("tool.search")


class RetrievalError(RuntimeError):
    pass


async def search_content(
    query: str,
    lang: str,
    top_k: int = 6,
    source_types: list[str] | None = None,
    score_threshold: float | None = None,
    intent: str | None = None,
) -> list[Chunk]:
    """Read-only search tool (design §5.5.1). Never touches the network."""
    try:
        return await _search(
            query,
            lang,
            top_k=top_k,
            source_types=source_types,
            score_threshold=score_threshold,
            intent=intent,
        )
    except Exception as exc:  # noqa: BLE001 - node decides the fallback
        raise RetrievalError(str(exc)) from exc


def chunks_as_dicts(chunks: list[Chunk]) -> list[dict[str, Any]]:
    from app.rag.retriever import chunk_to_dict

    return [chunk_to_dict(c) for c in chunks]
