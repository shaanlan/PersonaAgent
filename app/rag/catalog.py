from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.i18n import normalize_locale


@dataclass
class PageRef:
    page_type: str
    title: str
    url: str
    locale: str
    mbti_type: str | None = None
    slug: str | None = None
    summary: str = ""


class Catalog:
    """Deterministic page directory used by lookup_page (design §5.5.2)."""

    def __init__(self, pages: list[PageRef]) -> None:
        self.pages = pages

    @classmethod
    def from_documents(cls, docs: list[dict[str, Any]]) -> Catalog:
        pages: list[PageRef] = []
        for doc in docs:
            pages.append(
                PageRef(
                    page_type=doc.get("page_type") or doc.get("source_type") or "page",
                    title=doc.get("title", ""),
                    url=doc.get("url_path", ""),
                    locale=doc.get("locale", "zh-CN"),
                    mbti_type=doc.get("mbti_type") or None,
                    slug=doc.get("slug") or None,
                    summary=(doc.get("content") or "").split("\n")[0][:120].lstrip("# ").strip(),
                )
            )
        return cls(pages)

    @classmethod
    def load(cls, path: str) -> Catalog:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        pages = [PageRef(**item) for item in payload.get("pages", [])]
        return cls(pages)

    def dump(self) -> dict[str, Any]:
        return {"pages": [asdict(p) for p in self.pages]}

    def lookup(
        self,
        page_type: str,
        locale: str,
        slug: str | None = None,
        mbti_type: str | None = None,
    ) -> PageRef | None:
        locale = normalize_locale(locale)
        wanted_type = (mbti_type or "").upper() or None
        for page in self.pages:
            if page.locale != locale or page.page_type != page_type:
                continue
            if wanted_type and (page.mbti_type or "").upper() != wanted_type:
                continue
            if slug and page.slug != slug:
                continue
            if wanted_type or slug:
                return page
        if not wanted_type and not slug:
            for page in self.pages:
                if page.locale == locale and page.page_type == page_type:
                    return page
        return None


_catalog: Catalog | None = None
_catalog_lock = threading.Lock()


def load_corpus() -> dict[str, Any]:
    corpus_path = Path(__file__).parent / "data" / "mock_corpus.json"
    return json.loads(corpus_path.read_text(encoding="utf-8"))


def get_catalog() -> Catalog:
    global _catalog
    with _catalog_lock:
        if _catalog is None:
            settings = get_settings()
            if settings.catalog_path and Path(settings.catalog_path).exists():
                _catalog = Catalog.load(settings.catalog_path)
            else:
                _catalog = Catalog.from_documents(load_corpus()["docs"])
        return _catalog


def reset_catalog() -> None:
    global _catalog
    with _catalog_lock:
        _catalog = None
