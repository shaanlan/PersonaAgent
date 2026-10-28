from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache
def load_prompt(role: str, version: str = "v1") -> str:
    path = PROMPTS_DIR / role / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def fill(template: str, **values: str) -> str:
    """Replace {name} placeholders; unknown placeholders are left untouched."""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, match.group(0))

    return re.sub(r"\{(\w+)\}", repl, template)


LOCALE_NAMES = {
    "zh-CN": "简体中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "es": "Español",
    "pt-BR": "Português (Brasil)",
}
