from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import get_settings
from app.rag.embeddings import cosine

try:
    import chromadb

    CHROMA_AVAILABLE = True
except ImportError:  # pragma: no cover - only without the [rag] extra
    chromadb = None  # type: ignore[assignment]
    CHROMA_AVAILABLE = False


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    locale: str
    source_type: str
    page_type: str
    title: str
    section: str
    url_path: str
    text: str
    mbti_type: str | None = None
    slug: str | None = None
    keywords: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)
    score: float = 0.0

    def metadata(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "locale": self.locale,
            "source_type": self.source_type,
            "page_type": self.page_type,
            "title": self.title,
            "section": self.section,
            "url_path": self.url_path,
            "mbti_type": self.mbti_type or "",
            "slug": self.slug or "",
        }


class VectorStore(Protocol):
    name: str

    async def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...

    async def query(
        self, vector: list[float], top_k: int, locale: str | None = None, source_types: list[str] | None = None
    ) -> list[tuple[Chunk, float]]: ...

    async def scan(
        self, locale: str | None = None, source_types: list[str] | None = None, limit: int = 5000
    ) -> list[Chunk]: ...

    def info(self) -> dict[str, Any]: ...


class InMemoryStore:
    """Cosine in-memory store used when Chroma is not configured/installed."""

    name = "memory"

    def __init__(self) -> None:
        self._items: list[tuple[Chunk, list[float]]] = []
        self._lock = threading.Lock()

    async def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks/vectors length mismatch")
        with self._lock:
            self._items.extend(zip(chunks, vectors, strict=False))

    async def query(
        self, vector: list[float], top_k: int, locale: str | None = None, source_types: list[str] | None = None
    ) -> list[tuple[Chunk, float]]:
        results: list[tuple[Chunk, float]] = []
        with self._lock:
            items = list(self._items)
        for chunk, stored in items:
            if locale and chunk.locale != locale:
                continue
            if source_types and chunk.source_type not in source_types:
                continue
            results.append((chunk, cosine(vector, stored)))
        results.sort(key=lambda item: -item[1])
        return results[:top_k]

    def info(self) -> dict[str, Any]:
        with self._lock:
            count = len(self._items)
            dim = len(self._items[0][1]) if self._items else 0
        return {"name": self.name, "count": count, "dim": dim}

    async def scan(
        self, locale: str | None = None, source_types: list[str] | None = None, limit: int = 5000
    ) -> list[Chunk]:
        with self._lock:
            items = list(self._items)
        out: list[Chunk] = []
        for chunk, _ in items:
            if locale and chunk.locale != locale:
                continue
            if source_types and chunk.source_type not in source_types:
                continue
            out.append(chunk)
            if len(out) >= limit:
                break
        return out

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class ChromaStore:
    name = "chroma"

    def __init__(self) -> None:
        settings = get_settings()
        if not CHROMA_AVAILABLE:
            raise RuntimeError("chromadb is not installed; install with: uv sync --extra rag")
        self._client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self._collection = self._client.get_or_create_collection(settings.chroma_collection)

    async def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        self._collection.upsert(
            ids=[c.chunk_id for c in chunks],
            embeddings=vectors,
            documents=[c.text for c in chunks],
            metadatas=[c.metadata() for c in chunks],
        )

    async def query(
        self, vector: list[float], top_k: int, locale: str | None = None, source_types: list[str] | None = None
    ) -> list[tuple[Chunk, float]]:
        where: dict[str, Any] | None = None
        clauses: list[dict[str, Any]] = []
        if locale:
            clauses.append({"locale": locale})
        if source_types:
            clauses.append({"source_type": {"$in": source_types}})
        if len(clauses) == 1:
            where = clauses[0]
        elif clauses:
            where = {"$and": clauses}
        result = self._collection.query(
            query_embeddings=[vector], n_results=top_k, where=where, include=["documents", "metadatas", "distances"]
        )
        chunks: list[Chunk] = []
        scores: list[float] = []
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        for chunk_id, doc, meta, dist in zip(ids, docs, metas, dists, strict=False):
            meta = meta or {}
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    doc_id=meta.get("doc_id", ""),
                    locale=meta.get("locale", ""),
                    source_type=meta.get("source_type", ""),
                    page_type=meta.get("page_type", ""),
                    title=meta.get("title", ""),
                    section=meta.get("section", ""),
                    url_path=meta.get("url_path", ""),
                    text=doc or "",
                    mbti_type=meta.get("mbti_type") or None,
                    slug=meta.get("slug") or None,
                )
            )
            scores.append(max(0.0, 1.0 - float(dist)))
        return list(zip(chunks, scores, strict=False))

    async def scan(
        self, locale: str | None = None, source_types: list[str] | None = None, limit: int = 5000
    ) -> list[Chunk]:
        clauses: list[dict[str, Any]] = []
        if locale:
            clauses.append({"locale": locale})
        if source_types:
            clauses.append({"source_type": {"$in": source_types}})
        where: dict[str, Any] | None = None
        if len(clauses) == 1:
            where = clauses[0]
        elif clauses:
            where = {"$and": clauses}
        result = self._collection.get(where=where, limit=limit, include=["documents", "metadatas"])
        ids = result.get("ids") or []
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        return [
            Chunk(
                chunk_id=chunk_id,
                doc_id=(meta or {}).get("doc_id", ""),
                locale=(meta or {}).get("locale", ""),
                source_type=(meta or {}).get("source_type", ""),
                page_type=(meta or {}).get("page_type", ""),
                title=(meta or {}).get("title", ""),
                section=(meta or {}).get("section", ""),
                url_path=(meta or {}).get("url_path", ""),
                text=doc or "",
                mbti_type=(meta or {}).get("mbti_type") or None,
                slug=(meta or {}).get("slug") or None,
            )
            for chunk_id, doc, meta in zip(ids, docs, metas, strict=False)
        ]

    def info(self) -> dict[str, Any]:
        count = self._collection.count()
        return {"name": self.name, "count": count, "collection": self._collection.name}


_store: VectorStore | None = None
_store_lock = threading.Lock()


def get_vector_store() -> VectorStore:
    global _store
    with _store_lock:
        if _store is None:
            settings = get_settings()
            provider = settings.embedding_provider.lower()
            use_chroma = provider != "mock" and CHROMA_AVAILABLE and settings.chroma_persist_dir
            _store = ChromaStore() if use_chroma else InMemoryStore()
        return _store


def reset_vector_store() -> None:
    global _store
    with _store_lock:
        _store = None
