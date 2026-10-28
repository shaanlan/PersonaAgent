from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.nodes.finalize import finalize
from app.agent.nodes.generate import generate
from app.agent.nodes.guardrail import guardrail
from app.agent.nodes.load_context import load_context
from app.agent.nodes.personal_report import load_personal_report
from app.agent.nodes.retrieve import retrieve
from app.agent.nodes.rewrite_query import rewrite_query
from app.agent.nodes.route import route
from app.agent.state import ChatState

NODE_ORDER = [
    "load_context",
    "route",
    "load_personal_report",
    "retrieve",
    "rewrite_query",
    "generate",
    "guardrail",
    "finalize",
]


def route_decision(state: ChatState) -> str:
    """Conditional edge after `route` (design §5.4)."""
    if state.get("intent") in {"unsafe", "off_topic", "small_talk"}:
        return "guardrail"
    if state.get("need_personal_report") and state.get("user"):
        return "personal_report"
    return "retrieve"


def retrieve_decision(state: ChatState) -> str:
    """Conditional edge after `retrieve`: sufficient or retry budget exhausted -> generate (§5.4)."""
    if state.get("retrieval_sufficient") or state.get("retrieval_attempts", 0) >= 2:
        return "generate"
    return "rewrite_query"


def build_graph():
    builder = StateGraph(ChatState)
    builder.add_node("load_context", load_context)
    builder.add_node("route", route)
    builder.add_node("load_personal_report", load_personal_report)
    builder.add_node("retrieve", retrieve)
    builder.add_node("rewrite_query", rewrite_query)
    builder.add_node("generate", generate)
    builder.add_node("guardrail", guardrail)
    builder.add_node("finalize", finalize)

    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "route")
    builder.add_conditional_edges(
        "route",
        route_decision,
        {"guardrail": "guardrail", "personal_report": "load_personal_report", "retrieve": "retrieve"},
    )
    builder.add_edge("load_personal_report", "retrieve")
    builder.add_conditional_edges(
        "retrieve",
        retrieve_decision,
        {"generate": "generate", "rewrite_query": "rewrite_query"},
    )
    builder.add_edge("rewrite_query", "retrieve")
    builder.add_edge("generate", "finalize")
    builder.add_edge("guardrail", "finalize")
    builder.add_edge("finalize", END)
    # No checkpointer by design (§3.4): state is rebuilt from MySQL messages per request.
    return builder.compile()


GRAPH = build_graph()
