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

    s = get_settings()
    monkeypatch.setattr(s, "max_inflight_requests", 1)
    monkeypatch.setattr(s, "admission_wait_s", 0.1)
    app = create_app()

    @app.get(f"{s.api_prefix}/__test/slow")
    async def _slow() -> dict[str, str]:
        await asyncio.sleep(1.0)
        return {"ok": "yes"}

    client = TestClient(app)
    first: dict[str, int] = {}
    t = threading.Thread(
        target=lambda: first.update(code=client.get(f"{s.api_prefix}/__test/slow").status_code)
    )
    t.start()
    time.sleep(0.3)  # the first request now holds the only slot
    t0 = time.perf_counter()
    shed = client.get(f"{s.api_prefix}/__test/slow")
    waited = time.perf_counter() - t0
    assert shed.status_code == 503 and shed.json()["error"]["code"] == "server_busy"
    assert shed.headers["retry-after"] == "2"
    assert waited < 0.6  # shed after admission_wait_s, not after the slow request finished
    assert client.get(f"{s.api_prefix}/health").status_code == 200  # probes are never shed
    t.join()
    assert first["code"] == 200
    assert client.get(f"{s.api_prefix}/__test/slow").status_code == 200  # the slot was released
