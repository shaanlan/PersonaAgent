from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import NotFoundError, UnauthorizedError
from app.core.ids import request_id as new_request_id
from app.core.security import decode_uid, hash_session_token, parse_bearer, verify_internal_service_token
from app.db.models import ChatSession
from app.db.repositories import SessionRepository
from app.db.session import get_db


@dataclass
class Identity:
    uid: int | None = None
    bearer: str | None = None
    session_token: str | None = None
    is_internal: bool = False

    @property
    def has_credentials(self) -> bool:
        return self.uid is not None or self.session_token is not None

    @property
    def session_token_hash(self) -> str | None:
        return hash_session_token(self.session_token) if self.session_token else None


def get_request_id(request: Request) -> str:
    header = request.headers.get("X-Request-Id")
    if header:
        return header
    state_id = getattr(request.state, "request_id", None)
    return state_id or new_request_id()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def ip_hash(ip: str) -> str:
    settings = get_settings()
    return hashlib.sha256(f"{ip}|{settings.auth_jwt_secret}".encode()).hexdigest()


def user_agent_hash(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    settings = get_settings()
    return hashlib.sha256(f"{user_agent}|{settings.auth_jwt_secret}".encode()).hexdigest()


async def get_identity(
    authorization: str | None = Header(default=None),
    x_chat_session_token: str | None = Header(default=None, alias="X-Chat-Session-Token"),
    x_internal_service_token: str | None = Header(default=None, alias="X-Internal-Service-Token"),
) -> Identity:
    bearer = parse_bearer(authorization)
    uid = decode_uid(bearer)
    token = x_chat_session_token.strip() if x_chat_session_token and x_chat_session_token.strip() else None
    internal = verify_internal_service_token(x_internal_service_token)
    return Identity(uid=uid, bearer=bearer, session_token=token, is_internal=internal)


async def resolve_session(
    session_id: str,
    identity: Identity,
    db: AsyncSession,
) -> ChatSession:
    """Load a session and enforce the access matrix (design §9.12).

    - no credentials at all -> 401
    - credentials present but no match (uid or token) -> 404 (avoid enumeration)
    - match -> touch (sliding TTL) and return
    """
    settings = get_settings()
    repo = SessionRepository(db)
    session = await repo.get(session_id, ttl_days=settings.session_ttl_days)
    if session is None:
        raise NotFoundError("session not found")

    token = identity.session_token
    token_match = token is not None and hmac.compare_digest(hash_session_token(token), session.session_token_hash)
    uid_match = identity.uid is not None and session.uid == identity.uid

    if not (token_match or uid_match):
        if not identity.has_credentials:
            raise UnauthorizedError("X-Chat-Session-Token or Authorization required")
        raise NotFoundError("session not found")

    await repo.touch(session)
    return session


async def get_identity_dep(identity: Identity = Depends(get_identity)) -> Identity:
    return identity


async def get_db_dep(db: AsyncSession = Depends(get_db)) -> AsyncSession:
    return db
