from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("personality")

MOCK_REPORT: dict[str, Any] = {
    "result_type": "INFP",
    "confidence": 7200,
    "scores": [
        {"dimension": "E/I", "score": 28},
        {"dimension": "S/N", "score": 74},
        {"dimension": "T/F", "score": 68},
        {"dimension": "J/P", "score": 41},
    ],
}


@dataclass
class PersonalReport:
    """Minimal report context (design §12.3): type + confidence + scores only."""

    result_type: str
    confidence: int
    scores: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"result_type": self.result_type, "confidence": self.confidence, "scores": self.scores}


class PersonalityClient:
    """Client for the existing Go report API (design §12.3).

    Empty PERSONALITY_API_BASE_URL means mock mode, so the personal-report
    flow works without the Go backend.
    """

    async def _get(
        self, client: httpx.AsyncClient, url: str, params: dict[str, Any], headers: dict[str, str]
    ) -> httpx.Response | None:
        response: httpx.Response | None = None
        for attempt in range(2):
            try:
                response = await client.get(url, params=params, headers=headers)
            except Exception:  # noqa: BLE001 - network errors degrade to "no report"
                return None
            if response.status_code < 500 or attempt == 1:
                break
            await asyncio.sleep(0.3)
        return response

    async def get_latest_self_report(self, bearer_token: str | None) -> PersonalReport | None:
        if not bearer_token:
            return None
        settings = get_settings()
        if not settings.personality_api_base_url:
            return self._mock()
        base = settings.personality_api_base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {bearer_token}"}
        timeout = settings.personality_api_timeout_seconds
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                listing = await self._get(
                    client,
                    f"{base}/api/v1/personality/auth/reports",
                    {"perspective": "self", "limit": 1},
                    headers,
                )
                if listing is None or listing.status_code in (401, 404):
                    log.info("report_fetch", result="empty")
                    return None
                if listing.status_code >= 500:
                    log.warning("report_fetch", result="error", status=listing.status_code)
                    return None
                if listing.status_code != 200:
                    log.info("report_fetch", result="empty", status=listing.status_code)
                    return None
                payload = listing.json()
                items = payload.get("items") or payload.get("reports") or []
                if not items:
                    log.info("report_fetch", result="empty")
                    return None
                report_id = items[0].get("report_id") or items[0].get("id")
                detail = await self._get(
                    client,
                    f"{base}/api/v1/personality/report",
                    {"report_id": report_id},
                    headers,
                )
                if detail is None or detail.status_code != 200:
                    log.info("report_fetch", result="empty", status=getattr(detail, "status_code", None))
                    return None
                body = detail.json()
                report = self._extract(body.get("report", body))
                log.info("report_fetch", result="ok" if report else "empty")
                return report
        except Exception as exc:  # noqa: BLE001 - never break the answer path
            log.warning("report_fetch", result="error", error=type(exc).__name__)
            return None

    @staticmethod
    def _extract(payload: dict[str, Any]) -> PersonalReport | None:
        result_type = payload.get("result_type") or payload.get("type")
        if not result_type:
            return None
        return PersonalReport(
            result_type=str(result_type),
            confidence=int(payload.get("confidence") or 0),
            scores=list(payload.get("scores") or []),
        )

    @staticmethod
    def _mock() -> PersonalReport:
        return PersonalReport(
            result_type=MOCK_REPORT["result_type"],
            confidence=MOCK_REPORT["confidence"],
            scores=list(MOCK_REPORT["scores"]),
        )


_client: PersonalityClient | None = None


def get_personality_client() -> PersonalityClient:
    global _client
    if _client is None:
        _client = PersonalityClient()
    return _client
