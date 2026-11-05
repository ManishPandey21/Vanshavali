"""Fixed-window rate limiter (Redis in production, in-memory for tests/dev).

Windows are aligned to the clock: a 60-second limit counts hits in each wall-clock minute. The
clock is injectable (``clock``, default ``time.time``) so tests can pin it: with the real clock, a
test's requests can straddle a window boundary and be split across two windows, so no single window
ever goes over the limit and the expected 429 never comes.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from functools import lru_cache

from app.core.config import get_settings
from app.core.errors import TooManyRequests

Clock = Callable[[], float]


def window_index(now: float, window: int) -> int:
    """The fixed window ``now`` falls in (windows of ``window`` seconds, aligned to the epoch)."""
    return int(now) // window


class _MemoryLimiter:
    def __init__(self, clock: Clock = time.time) -> None:
        self.clock = clock
        self._lock = threading.Lock()
        self._counts: dict[str, tuple[int, int]] = {}

    def hit(self, key: str, limit: int, window: int) -> bool:
        now_window = window_index(self.clock(), window)
        with self._lock:
            win, count = self._counts.get(key, (now_window, 0))
            if win != now_window:
                win, count = now_window, 0
            count += 1
            self._counts[key] = (win, count)
            return count <= limit

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


class _RedisLimiter:
    def __init__(self, url: str, clock: Clock = time.time, client: object | None = None) -> None:
        import redis

        self.clock = clock
        self._r = client if client is not None else redis.Redis.from_url(url)

    def hit(self, key: str, limit: int, window: int) -> bool:
        bucket = f"rl:{key}:{window_index(self.clock(), window)}"
        pipe = self._r.pipeline()  # type: ignore[attr-defined]
        pipe.incr(bucket)
        pipe.expire(bucket, window)
        count, _ = pipe.execute()
        return int(count) <= limit

    def reset(self) -> None:  # pragma: no cover - test helper only
        pass


@lru_cache
def get_limiter() -> _MemoryLimiter | _RedisLimiter:
    s = get_settings()
    return _RedisLimiter(s.redis_url) if s.rate_limit_backend == "redis" else _MemoryLimiter()


def enforce(key: str, limit: int, window_seconds: int = 60) -> None:
    if not get_limiter().hit(key, limit, window_seconds):
        raise TooManyRequests("Too many attempts. Please wait a minute and try again.")
