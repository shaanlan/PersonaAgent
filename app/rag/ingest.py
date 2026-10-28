from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.rag.catalog import Catalog, load_corpus, reset_catalog
from app.rag.chunker import chunk_document
from app.rag.embeddings import embedding_config, get_embedding_provider
from app.rag.normalizer import normalize_markdown
from app.rag.scanner import RawDocument, scan_snapshot
from app.rag.store import Chunk, get_vector_store

log = get_logger("rag.ingest")


def _corpus_documents() -> list[RawDocument]:
    payload = load_corpus()
    docs: list[RawDocument] = []
    for item in payload["docs"]:
        docs.append(
            RawDocument(
                path=item["doc_id"],
                locale=item["locale"],
                source_type=item["source_type"],
                page_type=item.get("page_type", "page"),
                title=item["title"],
                slug=item.get("slug"),
                mbti_type=item.get("mbti_type"),
                url_path=item["url_path"],
                content=item["content"],
                keywords=list(item.get("keywords", [])),
            )
        )
    return docs


def _prepare(docs: list[RawDocument]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in docs:
        doc.content = normalize_markdown(doc.content)
        chunks.extend(chunk_document(doc))
    return chunks


async def _embed_and_store(chunks: list[Chunk]) -> dict[str, Any]:
    provider = get_embedding_provider()
    store = get_vector_store()
    vectors: list[list[float]] = []
    batch = 16
    for start in range(0, len(chunks), batch):
        part = chunks[start : start + batch]
        vectors.extend(await provider.embed([c.text for c in part]))
    await store.add(chunks, vectors)
    return {**embedding_config(), "chunks": len(chunks), "store": store.info()}


async def build_mock_index() -> dict[str, Any]:
    """Build the index from the built-in mock corpus (design §7.9 fallback)."""
    chunks = _prepare(_corpus_documents())
    stats = await _embed_and_store(chunks)
    reset_catalog()
    log.info("mock_index_built", **{k: v for k, v in stats.items() if k != "store"})
    return stats


async def ensure_index() -> dict[str, Any]:
    store = get_vector_store()
    info = store.info()
    if info.get("count", 0) > 0:
        return info
    return await build_mock_index()


def ingest_snapshot(snapshot_dir: str, out_dir: str | None = None) -> dict[str, Any]:
    """Offline ingest CLI path (design §7.2/§7.10): scan -> clean -> chunk -> embed -> store."""
    docs = scan_snapshot(snapshot_dir)
    if not docs:
        raise SystemExit(f"no documents found under {snapshot_dir}")
    for doc in docs:
        doc.content = normalize_markdown(doc.content)
    chunks = _prepare(docs)
    stats = asyncio.run(_embed_and_store(chunks))
    catalog = Catalog.from_documents([d.__dict__ for d in docs])
    manifest = {
        "snapshot_id": get_settings().index_snapshot_id,
        "collection": get_settings().chroma_collection,
        "embedding_provider": stats["provider"],
        "embedding_model": stats["model"],
        "embedding_dim": stats["dim"],
        "chunk_count": len(chunks),
        "doc_count": len(docs),
        "created_at": datetime.now(UTC).isoformat(),
        "checksum": hashlib.sha256("".join(c.chunk_id for c in chunks).encode()).hexdigest(),
    }
    if out_dir:
        out = Path(out_dir)
        (out / "index").mkdir(parents=True, exist_ok=True)
        (out / "index" / "catalog.json").write_text(
            json.dumps(catalog.dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out / "index" / "index_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    reset_catalog()
    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build the persona-chat search index")
    parser.add_argument("--snapshot", help="content snapshot directory (Markdown/JSON)")
    parser.add_argument("--out", help="write catalog.json + index_manifest.json here")
    parser.add_argument("--mock", action="store_true", help="build from the built-in mock corpus")
    args = parser.parse_args(argv)
    if args.mock or not args.snapshot:
        stats = asyncio.run(build_mock_index())
        print(json.dumps(stats, ensure_ascii=False, indent=2, default=str))
        return
    manifest = ingest_snapshot(args.snapshot, args.out)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
