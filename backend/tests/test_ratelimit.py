"""Fixed-window rate limiter: limits, window expiry and isolation, with a controlled clock."""

from __future__ import annotations

import fakeredis
import pytest

from app.core.config import get_settings
from app.core.errors import TooManyRequests
from app.core.ratelimit import _MemoryLimiter, _RedisLimiter, enforce, get_limiter, window_index


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


START = 1_800_000_000.0  # exactly on a minute (and hour) boundary


def limiters(clock: Clock) -> list[_MemoryLimiter | _RedisLimiter]:
    return [_MemoryLimiter(clock), _RedisLimiter("redis://unused", clock, client=fakeredis.FakeRedis())]


@pytest.mark.parametrize("kind", ["memory", "redis"])
def test_exactly_the_limit_is_allowed_then_refused_for_the_rest_of_the_window(kind):
    clock = Clock(START)
    limiter = limiters(clock)[0 if kind == "memory" else 1]
    assert [limiter.hit("k", 3, 60) for _ in range(5)] == [True, True, True, False, False]
    clock.now = START + 59.999  # still the same window
    assert limiter.hit("k", 3, 60) is False


@pytest.mark.parametrize("kind", ["memory", "redis"])
def test_a_new_window_starts_fresh(kind):
    clock = Clock(START + 30)
    limiter = limiters(clock)[0 if kind == "memory" else 1]
    assert [limiter.hit("k", 2, 60) for _ in range(3)] == [True, True, False]
    clock.now = START + 60  # the next minute
    assert [limiter.hit("k", 2, 60) for _ in range(3)] == [True, True, False]


@pytest.mark.parametrize("kind", ["memory", "redis"])
def test_hits_either_side_of_a_boundary_count_in_different_windows(kind):
    """Documents the fixed-window behaviour (and why tests must pin the clock): a burst that
    straddles a boundary is split between two windows."""
    clock = Clock(START - 1)
    limiter = limiters(clock)[0 if kind == "memory" else 1]
    assert [limiter.hit("k", 2, 60) for _ in range(2)] == [True, True]
    clock.now = START
    assert [limiter.hit("k", 2, 60) for _ in range(2)] == [True, True]
    assert limiter.hit("k", 2, 60) is False


@pytest.mark.parametrize("kind", ["memory", "redis"])
def test_keys_and_window_lengths_are_independent(kind):
    clock = Clock(START + 10)
    limiter = limiters(clock)[0 if kind == "memory" else 1]
    assert [limiter.hit("login-email:a", 1, 60) for _ in range(2)] == [True, False]
    assert limiter.hit("login-email:b", 1, 60) is True
    assert limiter.hit("register-email:a", 1, 3600) is True
    clock.now = START + 70  # next minute, same hour
    assert limiter.hit("login-email:a", 1, 60) is True
    assert limiter.hit("register-email:a", 1, 3600) is False


def test_redis_buckets_expire_with_their_window():
    clock = Clock(START + 5)
    r = fakeredis.FakeRedis()
    limiter = _RedisLimiter("redis://unused", clock, client=r)
    limiter.hit("k", 5, 60)
    key = f"rl:k:{window_index(START + 5, 60)}"
    assert int(r.get(key)) == 1
    assert 0 < r.ttl(key) <= 60


def test_window_index():
    assert window_index(START, 60) == window_index(START + 59.9, 60)
    assert window_index(START + 60, 60) == window_index(START, 60) + 1
    assert window_index(START + 3599, 3600) == window_index(START, 3600)


def test_enforce_raises_429_after_the_limit_with_the_same_message():
    limiter = get_limiter()
    assert limiter.clock() == limiter.clock()  # pinned by conftest: one window for the whole test
    for _ in range(3):
        enforce("unit:enforce", 3)
    with pytest.raises(TooManyRequests) as exc:
        enforce("unit:enforce", 3)
    assert exc.value.status_code == 429
    assert exc.value.code == "rate_limited"
    assert "Too many attempts" in str(exc.value)


def test_production_uses_the_real_clock():
    import time

    assert _MemoryLimiter().clock is time.time
    assert _RedisLimiter("redis://unused", client=fakeredis.FakeRedis()).clock is time.time
    assert get_settings().login_rate_limit_per_minute == 10  # thresholds unchanged
    assert get_settings().register_rate_limit_per_minute == 20
