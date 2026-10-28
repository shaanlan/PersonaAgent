from __future__ import annotations

import base64
import hashlib
import hmac
import os

import jwt

from app.core.config import get_settings
from app.core.errors import UnauthorizedError


def generate_session_token() -> str:
    raw = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    return f"st_{raw}"


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_session_token(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_session_token(token), token_hash)


def parse_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


def decode_uid(token: str | None) -> int | None:
    """Validate a Bearer token and return uid. Invalid/absent tokens return None.

    Anonymous endpoints treat None as anonymous (design §12.2).
    When AUTH_JWT_SECRET is not configured (dev mode), a ``mock:<uid>`` token is accepted
    so login-dependent flows can be exercised without the Go backend.
    """
    if not token:
        return None
    settings = get_settings()
    if not settings.jwt_configured:
        if token.startswith("mock:"):
            try:
                return int(token[5:])
            except ValueError:
                return None
        return None
    try:
        claims = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.auth_jwt_algorithm],
            issuer=settings.auth_jwt_issuer or None,
            audience=settings.auth_jwt_audience or None,
            options={"require": ["sub", "exp"]},
        )
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        return None


def require_uid(token: str | None) -> int:
    uid = decode_uid(token)
    if uid is None:
        raise UnauthorizedError("invalid or missing bearer token")
    return uid


def verify_internal_service_token(token: str | None) -> bool:
    settings = get_settings()
    if not settings.internal_service_token or not token:
        return False
    return hmac.compare_digest(token, settings.internal_service_token)
