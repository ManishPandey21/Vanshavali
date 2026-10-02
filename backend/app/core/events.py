"""Operational event counters shared by the API and the background worker.

The worker has no HTTP endpoint, so what happens there (job outcomes and durations, email delivery
failures, OCR failures, storage read errors) is counted in Redis when jobs run through RQ, and every
API replica exposes the shared totals in ``/metrics`` (aggregate them with ``max``, not ``sum``).
Without Redis (``JOB_MODE=sync``) the counters live in the process.

Only fixed, low-cardinality names are recorded: never user input, IDs or addresses. Recording never
raises: telemetry must not fail a job or a request.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any

from app.core.config import get_settings

log = logging.getLogger(__name__)

_KEY = "vsh:metrics:v1"
_lock = threading.Lock()
_local: dict[str, float] = defaultdict(float)
_redis: Any = None


def _client() -> Any:
    global _redis
    if get_settings().job_mode != "rq":
        return None
    if _redis is None:
        import redis

        _redis = redis.Redis.from_url(get_settings().redis_url, socket_timeout=1)
    return _redis


def _add(fields: dict[str, float]) -> None:
    try:
        r = _client()
        if r is None:
            with _lock:
                for k, v in fields.items():
                    _local[k] += v
            return
        pipe = r.pipeline(transaction=False)
        for k, v in fields.items():
            pipe.hincrbyfloat(_KEY, k, v)
        pipe.execute()
    except Exception as exc:  # pragma: no cover - telemetry must never break the caller
        log.warning("could not record metric: %s", type(exc).__name__)


def record(event: str) -> None:
    """Count one occurrence of a named operational event (e.g. ``mail_delivery_failed``)."""
    _add({f"event|{event}": 1})


def record_job(job: str, outcome: str, seconds: float) -> None:
    _add({f"job|{job}|{outcome}": 1, f"jobsec|{job}": seconds, f"jobcount|{job}": 1})


def snapshot() -> dict[str, float]:
    """All counters, from Redis when jobs use RQ, otherwise from this process."""
    try:
        r = _client()
        if r is None:
            with _lock:
                return dict(_local)
        return {k.decode(): float(v) for k, v in r.hgetall(_KEY).items()}
    except Exception as exc:
        log.warning("could not read shared metrics: %s", type(exc).__name__)
        return {}


def reset_local() -> None:
    """Tests only."""
    with _lock:
        _local.clear()
