from __future__ import annotations

from app.agent.nodes import emit
from app.agent.state import ChatState

_QUERY_ADDITIONS = {
    "career_fit": "职业 工作 建议",
    "relationship_content": "关系 相处 沟通",
    "relationship_match": "双人 配对 关系",
    "assess_other": "如何判断 他人 MBTI 类型",
    "mbti_concept": "MBTI 理论 原理 四个字母",
    "type_explore": "性格 类型 特点",
    "self_assess": "测试 维度 计分",
    "personal_report": "职业 工作 关系",
    "site_usage": "账号 报告 隐私",
}


async def rewrite_query(state: ChatState) -> dict:
    """Rewrite the search query when retrieval is insufficient (design §5.3.5/§7.6.3)."""
    intent = state.get("intent", "")
    addition = _QUERY_ADDITIONS.get(intent, "MBTI 类型")
    new_query = f"{state.get('search_query', '')} {addition}".strip()
    emit({"type": "log", "text": f"资料不足，改写查询 → {new_query}"})
    return {"search_query": new_query}
