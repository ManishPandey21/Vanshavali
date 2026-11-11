"""Overload behaviour (load test, Oct 2026).

Past capacity, request threads queued for the per-worker connection pool, waited the old 30 s
default, then failed as unhandled 500s while clients hung for up to 60 s (throughput collapsed to
below the offered rate). The pool wait is now short and configurable, and exhaustion is a
retryable 503.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.core.config import get_settings
from app.core.db import get_engine
from app.main import create_app


def test_pool_exhaustion_is_a_fast_retryable_503():
    app = create_app()

    @app.get("/__test/pool-exhausted")
    def _boom() -> None:
        raise PoolTimeoutError("QueuePool limit of size 5 overflow 10 reached")

    r = TestClient(app, raise_server_exceptions=False).get("/__test/pool-exhausted")
    assert r.status_code == 503
    assert r.headers["retry-after"] == "2"
    assert r.json()["error"]["code"] == "server_busy"
    assert "QueuePool" not in r.text  # no internals leak


def test_engine_uses_the_configured_pool():
    s = get_settings()
    pool = get_engine().pool
    assert pool.size() == s.db_pool_size  # type: ignore[attr-defined]
    assert pool._max_overflow == s.db_max_overflow  # type: ignore[attr-defined]
    assert pool._timeout == s.db_pool_timeout_s == 5.0  # type: ignore[attr-defined]


def test_admission_control_sheds_excess_quickly_and_spares_health(monkeypatch):
    import asyncio
    import threading
    import time

    # The slow request holds its slot until the test releases it (capped at HOLD_S). The shed
    # request must come back after about admission_wait_s; if admission control waited for the
    # slot instead, it would take at least HOLD_S. The bound sits between the two with wide
    # margins either side, so it does not depend on runner speed (a fixed 0.6 s bound with a
    # 1 s slow request flaked on shared CI runners).
    HOLD_S = 5.0
    WAIT_S = 0.1
    SHED_BOUND_S = WAIT_S + 1.5  # admission_wait_s plus scheduling/TestClient overhead
    assert SHED_BOUND_S < HOLD_S / 2

    s = get_settings()
    monkeypatch.setattr(s, "max_inflight_requests", 1)
    monkeypatch.setattr(s, "admission_wait_s", WAIT_S)
    app = create_app()
    holding = threading.Event()
    release = threading.Event()

    @app.get(f"{s.api_prefix}/__test/slow")
    async def _slow() -> dict[str, str]:
        holding.set()
        await asyncio.to_thread(release.wait, HOLD_S)
        return {"ok": "yes"}

    # One event loop for all requests (as in a real worker): without the context manager each
    # request gets its own loop, and a slot waiter would never be woken by a release.
    with TestClient(app) as client:
        first: dict[str, int] = {}
        t = threading.Thread(
            target=lambda: first.update(code=client.get(f"{s.api_prefix}/__test/slow").status_code)
        )
        t.start()
        try:
            assert holding.wait(HOLD_S)  # the first request now holds the only slot
            t0 = time.perf_counter()
            shed = client.get(f"{s.api_prefix}/__test/slow")
            waited = time.perf_counter() - t0
            assert shed.status_code == 503 and shed.json()["error"]["code"] == "server_busy"
            assert shed.headers["retry-after"] == "2"
            # shed after admission_wait_s, not after the slow request finished
            assert WAIT_S <= waited < SHED_BOUND_S
            assert client.get(f"{s.api_prefix}/health").status_code == 200  # probes are never shed
        finally:
            release.set()
            t.join()
        assert first["code"] == 200
        assert client.get(f"{s.api_prefix}/__test/slow").status_code == 200  # the slot was released
