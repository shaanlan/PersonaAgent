from __future__ import annotations

from app.agent.actions import build_actions
from app.agent.nodes import emit
from app.agent.state import ChatState
from app.agent.tools.get_latest_report import get_latest_self_report


async def load_personal_report(state: ChatState) -> dict:
    """Fetch the caller's latest self report (design §5.3.3/§12.4).

    Only type/confidence/scores are kept; report ids and raw content never enter state.
    """
    if not state.get("user") or not state.get("bearer_token"):
        emit({"type": "log", "text": "未登录，跳过个人报告"})
        return {"personal_report": None, "personal_report_used": False}

    report = await get_latest_self_report(state["bearer_token"])
    if report is None:
        emit({"type": "log", "text": "report_fetch=empty，走通用回答"})
        return {
            "personal_report": None,
            "personal_report_used": False,
            "clarify_question": "还没有可用的自测结果，先做一次自测就可以结合报告回答了。",
        }

    payload = report.as_dict()
    slots = dict(state.get("slots") or {})
    slots["mbti_type"] = report.result_type.upper()
    search_query = f"{state.get('search_query', '')} {report.result_type} 职业 工作 关系"
    actions = build_actions(state.get("intent", ""), slots, state.get("locale", "zh-CN"), payload)
    emit({"type": "log", "text": f"report_fetch=ok，result_type={report.result_type}（仅类型/置信度/维度分数入状态）"})
    return {
        "personal_report": payload,
        "personal_report_used": True,
        "slots": slots,
        "search_query": search_query,
        "actions": [a.model_dump() for a in actions],
    }
