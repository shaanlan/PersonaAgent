from __future__ import annotations

from app.rag.chunker import chunk_document, split_sections
from app.rag.normalizer import normalize_markdown
from app.rag.scanner import RawDocument


def test_split_sections_by_heading():
    content = "# Title\nintro\n## A\nbody a\n## B\nbody b"
    sections = split_sections(content)
    titles = [s for s, _ in sections]
    assert any("A" in t for t in titles)
    assert any("B" in t for t in titles)


def test_chunk_document_produces_multiple_chunks():
    doc = RawDocument(
        path="x",
        locale="zh-CN",
        source_type="type",
        page_type="type_detail",
        title="T",
        slug=None,
        mbti_type="INFP",
        url_path="/zh-CN/type/t",
        content="# T\n## one\n" + "甲。" * 400 + "\n## two\n乙。",
        keywords=[],
    )
    chunks = chunk_document(doc, target_chars=300, overlap_chars=50)
    assert len(chunks) >= 2
    assert all(c.url_path == "/zh-CN/type/t" for c in chunks)
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_normalize_strips_html_and_external_links():
    raw = "<!-- comment --><script>alert(1)</script>\n[点我](https://evil.com) 和 ![img](x.png) 文本"
    cleaned = normalize_markdown(raw)
    assert "<script>" not in cleaned
    assert "evil.com" not in cleaned
    assert "comment" not in cleaned
    assert "点我" in cleaned
    assert "img" in cleaned
