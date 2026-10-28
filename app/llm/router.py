from __future__ import annotations

from app.core.config import get_settings
from app.llm.client import LLMClient, get_llm_client

_ROLE_MODEL_ATTR = {
    "router": "llm_router_model",
    "answer": "llm_answer_model",
    "summary": "llm_summary_model",
}


def model_for_role(role: str) -> str:
    settings = get_settings()
    return getattr(settings, _ROLE_MODEL_ATTR.get(role, "llm_answer_model"))


def temperature_for_role(role: str) -> float:
    if role == "router":
        return 0.0
    if role == "summary":
        return 0.2
    return get_settings().llm_temperature


def get_client_for_role(role: str) -> tuple[LLMClient, str, float]:
    """Return (client, model, temperature) for a prompt role.

    Fallback model handling lives inside the LiteLLM client (design §8.2).
    """
    return get_llm_client(), model_for_role(role), temperature_for_role(role)
