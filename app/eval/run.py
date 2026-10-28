from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.agent.actions import build_actions, valid_url
from app.agent.nodes.route import route
from app.agent.state import ChatState
from app.core.intents import rule_precheck
from app.rag.ingest import ensure_index
from app.rag.retriever import search_content

GOLDEN_PATH = Path(__file__).parent / "golden.jsonl"

TARGETS = {
    "intent_accuracy": 0.90,
    "recall_at_5": 0.85,
    "link_valid_rate": 1.0,
}


def load_golden() -> list[dict[str, Any]]:
    rows = []
    for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


async def evaluate_intent(row: dict[str, Any]) -> bool:
    state: ChatState = {"user_message": row["q"], "locale": "zh-CN", "user": None}
    try:
        updates = await route(state)
        return updates.get("intent") == row["intent"]
    except Exception:  # noqa: BLE001
        return rule_precheck(row["q"]).intent.value == row["intent"]


async def evaluate_recall(row: dict[str, Any]) -> bool:
    expect = row.get("expect_url")
    if not expect:
        return True
    chunks = await search_content(row["q"], "zh-CN", intent=row["intent"])
    if not chunks:
        # Mirror the retrieve -> rewrite_query -> retrieve loop (design §5.4).
        from app.agent.nodes.rewrite_query import _QUERY_ADDITIONS

        rewritten = f"{row['q']} {_QUERY_ADDITIONS.get(row['intent'], 'MBTI 类型')}"
        chunks = await search_content(rewritten, "zh-CN", intent=row["intent"])
    urls = [c.url_path for c in chunks[:5]]
    return expect in urls


def evaluate_links(row: dict[str, Any]) -> bool:
    actions = build_actions(row["intent"], {}, "zh-CN", None)
    if not actions:
        return True
    return all(valid_url(a.url) for a in actions)


async def main() -> int:
    rows = load_golden()
    await ensure_index()

    intent_hits = 0
    recall_hits = 0
    recall_total = 0
    link_ok = 0
    failures: list[str] = []

    for row in rows:
        intent_ok = await evaluate_intent(row)
        intent_hits += int(intent_ok)
        if row.get("expect_url"):
            recall_total += 1
            recall_hit = await evaluate_recall(row)
            recall_hits += int(recall_hit)
        else:
            recall_hit = True
        links_ok = evaluate_links(row)
        link_ok += int(links_ok)
        if not (intent_ok and recall_hit and links_ok):
            failures.append(f"  - {row['q']!r}: intent_ok={intent_ok} recall_ok={recall_hit} links_ok={links_ok}")

    metrics = {
        "samples": len(rows),
        "intent_accuracy": round(intent_hits / len(rows), 3),
        "recall_at_5": round(recall_hits / recall_total, 3) if recall_total else 1.0,
        "link_valid_rate": round(link_ok / len(rows), 3),
    }
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    if failures:
        print("\nfailures:")
        print("\n".join(failures))

    below = {k: v for k, v in metrics.items() if k in TARGETS and v < TARGETS[k]}
    if below:
        print(f"\nFAIL: below targets {below}")
        return 1
    print("\nPASS: all targets met")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
