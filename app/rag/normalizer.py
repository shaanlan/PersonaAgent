from __future__ import annotations

import re

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_SCRIPT_RE = re.compile(r"<(script|style|iframe)[^>]*>.*?</\1>", re.S | re.I)
_EXTERNAL_URL_RE = re.compile(r"\[([^\]]+)\]\(https?://[^)]+\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


def normalize_markdown(text: str) -> str:
    """Cleaning rules from design §7.3."""
    text = _HTML_COMMENT_RE.sub("", text)
    text = _SCRIPT_RE.sub("", text)
    text = _IMAGE_RE.sub(r"\1", text)
    text = _EXTERNAL_URL_RE.sub(r"\1", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()
