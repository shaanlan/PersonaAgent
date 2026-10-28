from __future__ import annotations

import re

from app.rag.scanner import RawDocument
from app.rag.store import Chunk

_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$", re.M)


def split_sections(content: str) -> list[tuple[str, str]]:
    """Split markdown into (section_path, body) pairs by headings (design §7.4)."""
    matches = list(_HEADING_RE.finditer(content))
    if not matches:
        return [("", content.strip())]
    sections: list[tuple[str, str]] = []
    preamble = content[: matches[0].start()].strip()
    if preamble:
        sections.append(("", preamble))
    stack: list[str] = []
    for index, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        while len(stack) >= level:
            stack.pop()
        stack.append(title)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[match.end() : end].strip()
        if body:
            sections.append((" > ".join(stack), body))
    return sections


def _split_long(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= target_chars:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + target_chars)
        if end < len(text):
            window = text[start:end]
            cut = max(window.rfind("。"), window.rfind(". "), window.rfind("\n"))
            if cut > target_chars // 2:
                end = start + cut + 1
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return [p for p in parts if p]


def chunk_document(
    doc: RawDocument,
    *,
    target_chars: int = 700,
    overlap_chars: int = 100,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section, body in split_sections(doc.content):
        for _index, piece in enumerate(_split_long(body, target_chars, overlap_chars)):
            chunk_index = len(chunks)
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.url_path or doc.path}:{chunk_index}",
                    doc_id=doc.url_path or doc.path,
                    locale=doc.locale,
                    source_type=doc.source_type,
                    page_type=doc.page_type,
                    title=doc.title,
                    section=section,
                    url_path=doc.url_path,
                    text=piece,
                    mbti_type=doc.mbti_type,
                    slug=doc.slug,
                    keywords=list(doc.keywords),
                )
            )
    return chunks or [
        Chunk(
            chunk_id=f"{doc.url_path or doc.path}:0",
            doc_id=doc.url_path or doc.path,
            locale=doc.locale,
            source_type=doc.source_type,
            page_type=doc.page_type,
            title=doc.title,
            section="",
            url_path=doc.url_path,
            text=doc.content[:target_chars],
            mbti_type=doc.mbti_type,
            slug=doc.slug,
            keywords=list(doc.keywords),
        )
    ]
