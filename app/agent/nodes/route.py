from __future__ import annotations

from app.agent.actions import build_actions
from app.agent.nodes import emit
from app.agent.prompt_loader import fill, load_prompt
from app.agent.state import ChatState
from app.core.intents import normalize_type, rule_precheck
from app.core.logging import get_logger
from app.llm.litellm_client import parse_router_json
from app.llm.router import get_client_for_role
from app.schemas.intent import RouteResult, Slots

log = get_logger("agent.route")


async def route(state: ChatState) -> dict:
    """Hybrid routing: rule precheck + LLM structured output + validation (design §6.2)."""
    question = state["user_message"]
    locale = state.get("locale", "zh-CN")
    rule = rule_precheck(question)

    final = rule
    source = "rules"
    try:
        client, model, temperature = get_client_for_role("router")
        template = fill(load_prompt("router"), question=question)
        result = await client.complete(
            role="router",
            model=model,
            messages=[{"role": "user", "content": template}],
            temperature=temperature,
            hints={"question": question},
        )
        parsed = RouteResult.model_validate(parse_router_json(result.text))
        final = parsed
        source = "llm"
    except Exception as exc:  # noqa: BLE001 - design §5.9: fall back to rules
        log.info("router_fallback", error=type(exc).__name__)

    # Safety rules always win over the model (design §6.2.1).
    if rule.intent.value == "unsafe":
        final = rule
        source = "rules(safety)"

    slots = _normalize_slots(final.slots)
    clarify = final.clarify_question or (rule.clarify_question if final.confidence < 0.45 else None)
    if final.need_personal_report and not state.get("user"):
        clarify = "登录后我可以引用你最近一次自测报告；现在可以先给你通用建议。"

    search_query = final.search_query or question
    if slots.mbti_type and slots.mbti_type not in search_query:
        search_query = f"{search_query} {slots.mbti_type}"

    actions = build_actions(final.intent.value, slots, locale, None)
    emit(
        {
            "type": "log",
            "text": f"路由 source={source} → {final.intent.value}（置信度 {final.confidence:.2f}）",
        }
    )
    return {
        "intent": final.intent.value,
        "intent_confidence": final.confidence,
        "slots": slots.model_dump(exclude_none=True),
        "search_query": search_query,
        "need_personal_report": final.need_personal_report,
        "clarify_question": clarify,
        "actions": [a.model_dump() for a in actions],
    }


def _normalize_slots(slots: Slots) -> Slots:
    data = slots.model_dump()
    data["mbti_type"] = normalize_type(data.get("mbti_type"))
    data["type_a"] = normalize_type(data.get("type_a"))
    data["type_b"] = normalize_type(data.get("type_b"))
    return Slots(**data)
