from __future__ import annotations

from app.rag.catalog import PageRef, get_catalog


def lookup_page(
    page_type: str,
    lang: str,
    slug: str | None = None,
    mbti_type: str | None = None,
) -> PageRef | None:
    """Deterministic catalog lookup (design §5.5.2). No LLM involved."""
    return get_catalog().lookup(page_type, lang, slug=slug, mbti_type=mbti_type)
