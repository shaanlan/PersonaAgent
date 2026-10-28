from __future__ import annotations

import pytest

from app.core.errors import RateLimitedError, ValidationError
from app.core.rate_limit import ConcurrencyLimiter, SlidingWindowLimiter
from app.core.security import (
    decode_uid,
    generate_session_token,
    hash_session_token,
    verify_session_token,
)


def test_session_token_roundtrip():
    token = generate_session_token()
    assert token.startswith("st_")
    assert verify_session_token(token, hash_session_token(token))
    assert not verify_session_token("st_other", hash_session_token(token))


def test_session_token_hash_is_sha256_hex():
    token = generate_session_token()
    assert len(hash_session_token(token)) == 64


def test_dev_mode_accepts_mock_bearer(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "")
    from app.core.config import get_settings

    get_settings.cache_clear()
    assert decode_uid("mock:42") == 42
    assert decode_uid("garbage") is None
    assert decode_uid(None) is None
    get_settings.cache_clear()


def test_sliding_window_raises_429_with_retry_after():
    limiter = SlidingWindowLimiter()
    for _ in range(3):
        limiter.check("k", 3)
    with pytest.raises(RateLimitedError) as exc:
        limiter.check("k", 3)
    assert exc.value.retry_after is not None
    assert exc.value.status_code == 429


def test_concurrency_limiter_acquire_release():
    limiter = ConcurrencyLimiter()
    assert limiter.try_acquire("a", 1)
    assert not limiter.try_acquire("a", 1)
    limiter.release("a")
    assert limiter.try_acquire("a", 1)


def test_stream_slots_acquire_and_release(monkeypatch):
    from app.api.deps import Identity
    from app.services import chat_service

    monkeypatch.setattr(chat_service, "stream_limiter", ConcurrencyLimiter())

    first = chat_service.acquire_stream_slots(Identity(), "10.0.0.1")
    second = chat_service.acquire_stream_slots(Identity(), "10.0.0.1")
    # per-IP limit is 2 by default (design §12.7)
    with pytest.raises(RateLimitedError):
        chat_service.acquire_stream_slots(Identity(), "10.0.0.1")

    chat_service.release_stream_slots(first)
    chat_service.release_stream_slots(second)
    assert chat_service.stream_limiter.count("stream:ip:10.0.0.1") == 0
    assert chat_service.stream_limiter.count("stream:global") == 0


def test_validation_error_defaults():
    err = ValidationError("bad")
    assert err.status_code == 400
    assert err.code.value == "INVALID_ARGUMENT"
