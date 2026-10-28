from __future__ import annotations

import contextvars
import logging
import sys
from typing import Any

import structlog

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
session_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("session_id", default="-")

_SENSITIVE_KEYS = {"content", "answer", "user_message", "prompt", "token", "password", "secret"}


def setup_logging(level: str = "info", dev: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=getattr(logging, level.upper(), logging.INFO))
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if dev:
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(_redact)
        processors.append(structlog.processors.JSONRenderer())
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper(), logging.INFO)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _redact(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict):
        if key in _SENSITIVE_KEYS:
            event_dict[key] = "[redacted]"
        elif key.endswith("_text") or key.endswith("_content"):
            event_dict[key] = "[redacted]"
    return event_dict


def get_logger(name: str | None = None, **initial: Any) -> Any:
    return structlog.get_logger(name).bind(**initial)


def bind_request(request_id: str, session_id: str = "-") -> None:
    request_id_var.set(request_id)
    session_id_var.set(session_id)


def log_event(event: str, **fields: Any) -> None:
    get_logger().info(event, **fields)
