from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from app.core.intents import rule_precheck
from app.llm.client import LLMResult

_ZH_LEADS = {
    "type_explore": "{mbti} 的核心特征可以从能量来源、信息获取、决策方式和生活取向四个维度理解。",
    "career_fit": "关于 {mbti} 的职业方向，建议把 MBTI 当作偏好参考，而不是唯一结论。",
    "relationship_content": "在关系相处中，类型差异更多影响沟通偏好和冲突处理方式，而不是决定关系好坏。",
    "relationship_match": "两个人是否合适，不能只靠类型组合判断，还要看沟通、边界和共同目标。",
    "assess_other": "判断他人类型时，只能基于可观察行为做谨慎推测，最好邀请对方亲自完成测试。",
    "mbti_concept": "MBTI 的四个字母描述的是偏好倾向，不是能力高低，也不等同于心理诊断。",
    "personal_report": "结合你最近一次自测报告，可以从类型偏好出发理解职业和关系选择。",
    "self_assess": "自测结果反映的是当下的偏好倾向，建议隔一段时间复测，观察稳定趋势。",
    "site_usage": "登录后报告会保存到账号中，你可以在“我的报告”里查看历史结果。",
    "small_talk": "你好，我是 PersonaAgent 助手。你可以问我 MBTI 类型、职业适配、关系相处或测评相关的问题。",
    "off_topic": "我主要回答 MBTI 类型、测评、关系、职业和站点使用问题。",
    "unsafe": "我不能对自伤、暴力或医疗诊断相关话题做 MBTI 分析。",
}

_EN_LEADS = {
    "type_explore": "{mbti} can be understood along four axes: energy, information, decisions and lifestyle.",
    "career_fit": "For {mbti} career direction, treat MBTI as a preference reference rather than a single conclusion.",
    "relationship_content": "In relationships, type differences mostly shape communication "
    "and conflict styles, not the outcome.",
    "relationship_match": "Compatibility cannot be judged by type pairing alone; "
    "communication and boundaries matter more.",
    "assess_other": "Type others only from observable behavior, and prefer inviting them to take the test themselves.",
    "mbti_concept": "The four letters describe preferences, not ability, and never a clinical diagnosis.",
    "personal_report": "Using your latest self-test result, you can explore career "
    "and relationship choices by preference.",
    "self_assess": "A self-test reflects current preferences; retest later to observe stable trends.",
    "site_usage": "Sign in to keep reports in your account; you can review them under My Reports.",
    "small_talk": "Hi, I'm the PersonaAgent assistant. Ask me about MBTI types, careers, relationships or the quiz.",
    "off_topic": "I mainly answer questions about MBTI types, the quiz, relationships, careers and site usage.",
    "unsafe": "I can't analyze self-harm, violence or medical diagnosis topics through MBTI.",
}


def _compose_answer(hints: dict[str, Any]) -> str:
    intent = hints.get("intent", "off_topic")
    locale = hints.get("locale", "zh-CN")
    zh = locale.startswith("zh")
    leads = _ZH_LEADS if zh else _EN_LEADS
    mbti = hints.get("mbti") or ("这个类型" if zh else "this type")
    lead = leads.get(intent, leads["off_topic"]).format(mbti=mbti)

    lines: list[str] = []
    if not hints.get("sufficient", True):
        lines.append("（站内资料不足，以下是通用说明）" if zh else "(Not enough site content; general notes below)")
    lines.append(lead)

    report = hints.get("report")
    if report:
        if zh:
            lines.append(f"你最近一次自测结果是 {report['result_type']}（置信度 {report['confidence']}）。")
        else:
            lines.append(
                f"Your latest self-test result is {report['result_type']} (confidence {report['confidence']})."
            )

    retrieved = hints.get("retrieved") or []
    if retrieved:
        top = retrieved[0]
        if zh:
            lines.append(f"根据站内《{top['title']}》：{top['text'][:100]}")
        else:
            lines.append(f"According to “{top['title']}” on the site: {top['text'][:100]}")
    if len(retrieved) > 1:
        if zh:
            lines.append(f"另外《{retrieved[1]['title']}》也提供了相关背景。")
        else:
            lines.append(f"“{retrieved[1]['title']}” adds further background.")

    clarify = hints.get("clarify")
    if clarify:
        lines.append(clarify)

    if zh:
        lines.append("你可以查看下方来源，或继续问我一个具体场景。")
    else:
        lines.append("Check the sources below, or ask me a more specific scenario.")
    return "\n\n".join(lines)


class MockLLMClient:
    """Template LLM used when LLM_PROVIDER=mock (default).

    - router role: delegates to the rule engine so the structured-output path
      (prompt -> JSON -> Pydantic) is still exercised end to end.
    - answer role: streams a deterministic template built from `hints`.
    - summary role: truncates history into a short rolling summary.
    """

    provider = "mock"

    async def complete(
        self,
        *,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 300,
        hints: dict[str, Any] | None = None,
    ) -> LLMResult:
        hints = hints or {}
        if role == "router":
            question = hints.get("question") or (messages[-1]["content"] if messages else "")
            result = rule_precheck(question)
            text = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
        elif role == "summary":
            history = hints.get("history") or []
            joined = "；".join(f"{m.get('role')}: {str(m.get('content'))[:28]}" for m in history[-4:])
            text = joined[:200] if joined else "（暂无历史）"
        else:
            text = _compose_answer(hints)
        return LLMResult(
            text=text,
            model=f"mock/{model}",
            input_tokens=max(1, sum(len(m.get("content", "")) for m in messages) // 2),
            output_tokens=max(1, len(text) // 2),
            finish_reason="stop",
        )

    async def stream(
        self,
        *,
        role: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 600,
        hints: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        result = await self.complete(
            role=role,
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            hints=hints,
        )
        text = result.text[: max(1, max_tokens * 4)]
        for index in range(0, len(text), 4):
            yield text[index : index + 4]
            await _sleep()


async def _sleep() -> None:
    import asyncio

    await asyncio.sleep(0.012)
