"""Fixed-window rate limiter (Redis in production, in-memory for tests/dev)."""

from __future__ import annotations

import threading
import time
from functools import lru_cache

from app.core.config import get_settings
from app.core.errors import TooManyRequests


class _MemoryLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, tuple[int, int]] = {}

    def hit(self, key: str, limit: int, window: int) -> bool:
        now_window = int(time.time()) // window
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
    def __init__(self, url: str) -> None:
        import redis

        self._r = redis.Redis.from_url(url)

    def hit(self, key: str, limit: int, window: int) -> bool:
        bucket = f"rl:{key}:{int(time.time()) // window}"
        pipe = self._r.pipeline()
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
