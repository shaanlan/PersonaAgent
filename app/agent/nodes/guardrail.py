from __future__ import annotations

from app.agent.nodes import emit
from app.agent.state import ChatState

_COPY = {
    "unsafe": {
        "zh-CN": (
            "我不能对自伤、暴力或医疗诊断相关话题做 MBTI 分析。"
            "如果你正经历危险，请立即联系当地紧急服务或可信赖的人。"
            "你愿意先说说现在发生了什么吗？"
        ),
        "en": (
            "I can't analyze self-harm, violence or medical diagnosis topics through MBTI. "
            "If you are in danger, contact local emergency services or someone you trust right away. "
            "Would you like to tell me what happened?"
        ),
    },
    "small_talk": {
        "zh-CN": (
            "你好，我是 PersonaAgent 助手。你可以问我 MBTI 类型、职业适配、关系相处或测评相关的问题，"
            "例如“INFP 适合做什么职业？”。"
        ),
        "en": (
            "Hi, I'm the PersonaAgent assistant. Ask me about MBTI types, careers, "
            "relationships or the quiz, e.g. “What careers fit INFP?”"
        ),
    },
    "off_topic": {
        "zh-CN": (
            "我主要回答 MBTI 类型、测评、关系、职业和站点使用问题。"
            "你可以试试：“INTJ 是什么类型？”或“INFP 适合做什么职业？”"
        ),
        "en": (
            "I mainly answer questions about MBTI types, the quiz, relationships, careers "
            "and site usage. Try “What is INTJ like?” or “What careers fit INFP?”"
        ),
    },
}


async def guardrail(state: ChatState) -> dict:
    """Fixed-template safety / small-talk / off-topic branch (design §5.3.7). No LLM call."""
    intent = state.get("intent", "off_topic")
    locale = state.get("locale", "zh-CN")
    prompts = _COPY.get(intent, _COPY["off_topic"])
    if locale in prompts:
        answer = prompts[locale]
    elif locale.startswith("zh"):
        answer = prompts["zh-CN"]
    else:
        # Remaining locales fall back to English copy; full 6-language strings ship with FE i18n.
        answer = prompts["en"]

    emit({"type": "token", "delta": answer})
    return {
        "answer": answer,
        "actions": [],
        "sources": [],
        "retrieval_sufficient": False,
        "finish_reason": "stop",
        "model": "template/guardrail",
        "first_token_ms": 0,
        "latency_ms": 0,
        "usage": {"input_tokens": 0, "output_tokens": max(1, len(answer) // 2)},
        "degraded": False,
    }
