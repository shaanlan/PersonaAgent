from __future__ import annotations

import pytest

from app.agent.nodes.rewrite_query import _QUERY_ADDITIONS
from app.api.sse import make_event, sse_frame
from app.rag.ingest import ensure_index
from app.rag.retriever import build_sources, search_content


@pytest.mark.asyncio
async def test_search_returns_expected_page():
    await ensure_index()
    chunks = await search_content("INFP 适合做什么职业？", "zh-CN", intent="career_fit")
    urls = [c.url_path for c in chunks]
    assert "/zh-CN/career" in urls
    assert all(c.score >= 0.35 for c in chunks)


@pytest.mark.asyncio
async def test_search_locale_filter_falls_back():
    await ensure_index()
    en_chunks = await search_content("What careers fit INFP?", "en", intent="career_fit")
    assert en_chunks, "english corpus should be searchable"
    assert all(c.locale == "en" for c in en_chunks)


@pytest.mark.asyncio
async def test_sources_dedup_and_cap():
    await ensure_index()
    chunks = await search_content("INFP 适合做什么职业？", "zh-CN", intent="career_fit")
    sources = build_sources(chunks, max_sources=3)
    urls = [s.url for s in sources]
    assert len(urls) == len(set(urls))
    assert len(sources) <= 3


@pytest.mark.asyncio
async def test_rewrite_additions_cover_intents():
    await ensure_index()
    # first pass for a no-overlap phrasing comes back empty -> rewrite path
    first = await search_content("四个字母的原理是什么来着", "zh-CN", intent="mbti_concept")
    if not first:
        rewritten = "四个字母的原理是什么来着 " + _QUERY_ADDITIONS["mbti_concept"]
        second = await search_content(rewritten, "zh-CN", intent="mbti_concept")
        assert second, "rewrite should recover results"
    assert set(_QUERY_ADDITIONS) >= {"career_fit", "mbti_concept", "assess_other"}


def test_sse_frame_format():
    frame = sse_frame(make_event("token", delta="你好"))
    assert frame.startswith("event: token\ndata: ")
    assert frame.endswith("\n\n")
    assert "你好" in frame
