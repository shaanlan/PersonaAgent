from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


@dataclass
class RawDocument:
    path: str
    locale: str
    source_type: str
    page_type: str
    title: str
    slug: str | None
    mbti_type: str | None
    url_path: str
    content: str
    keywords: list[str]


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, text[match.end() :]


def scan_snapshot(root: str | Path) -> list[RawDocument]:
    """Scan a content snapshot directory for Markdown documents (design §7.2)."""
    base = Path(root)
    docs: list[RawDocument] = []
    for path in sorted(base.rglob("*.md")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        meta, body = parse_frontmatter(raw)
        rel = path.relative_to(base).as_posix()
        locale = str(meta.get("locale") or _guess_locale(rel))
        docs.append(
            RawDocument(
                path=rel,
                locale=locale,
                source_type=str(meta.get("source_type") or _guess_source_type(rel)),
                page_type=str(meta.get("page_type") or "page"),
                title=str(meta.get("title") or path.stem),
                slug=meta.get("slug") or None,
                mbti_type=meta.get("mbti_type") or None,
                url_path=str(meta.get("url_path") or f"/{locale}/{path.stem}"),
                content=body,
                keywords=[k.strip() for k in str(meta.get("keywords", "")).split(",") if k.strip()],
            )
        )
    for path in sorted(base.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for item in payload.get("docs", []):
            docs.append(
                RawDocument(
                    path=str(item.get("doc_id", path.stem)),
                    locale=str(item.get("locale", "zh-CN")),
                    source_type=str(item.get("source_type", "blog")),
                    page_type=str(item.get("page_type", "page")),
                    title=str(item.get("title", "")),
                    slug=item.get("slug"),
                    mbti_type=item.get("mbti_type"),
                    url_path=str(item.get("url_path", "")),
                    content=str(item.get("content", "")),
                    keywords=list(item.get("keywords", [])),
                )
            )
    return docs


def _guess_locale(rel: str) -> str:
    first = rel.split("/", 1)[0]
    return first if len(first) <= 10 else "zh-CN"


def _guess_source_type(rel: str) -> str:
    for key in ("type", "career", "relationship", "blog", "about", "quiz"):
        if key in rel:
            return "site_help" if key == "about" else ("test_meta" if key == "quiz" else key)
    return "blog"
