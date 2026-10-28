from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.core.errors import RateLimitedError


class SlidingWindowLimiter:
    """In-process sliding window limiter (design §12.7, single worker)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        with self._lock:
            queue = self._hits[key]
            cutoff = now - window_seconds
            while queue and queue[0] <= cutoff:
                queue.popleft()
            if len(queue) >= limit:
                retry_after = max(1, int(queue[0] + window_seconds - now) + 1)
                raise RateLimitedError(retry_after=retry_after)
            queue.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class ConcurrencyLimiter:
    """Counts in-flight streams per key with a hard global ceiling."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def try_acquire(self, key: str, limit: int) -> bool:
        if limit <= 0:
            return True
        with self._lock:
            if self._counts[key] >= limit:
                return False
            self._counts[key] += 1
            return True

    def release(self, key: str) -> None:
        with self._lock:
            if self._counts[key] > 0:
                self._counts[key] -= 1

    def count(self, key: str) -> int:
        with self._lock:
            return self._counts[key]


rate_limiter = SlidingWindowLimiter()
stream_limiter = ConcurrencyLimiter()
