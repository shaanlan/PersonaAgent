from __future__ import annotations

from app.services.personality_client import PersonalReport, get_personality_client


async def get_latest_self_report(bearer_token: str | None) -> PersonalReport | None:
    """Read the caller's latest self report (design §5.5.3).

    Never returns other users' reports, never logs report contents.
    """
    if not bearer_token:
        return None
    return await get_personality_client().get_latest_self_report(bearer_token)
