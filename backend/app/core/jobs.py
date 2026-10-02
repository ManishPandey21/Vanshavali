"""Background jobs: inline (tests/single-process dev) or Redis + RQ (production).

Every job runs through :func:`run_job`, which times it and records its outcome
(:mod:`app.core.events`), so job failures, email failures and OCR durations are visible in
``/metrics`` even though they happen in the worker process.

Job descriptions name the function only. RQ's default description is the call with its arguments,
which the worker logs at INFO and keeps in Redis; for email jobs that put the recipient's address
and subject into the worker log (pilot audit, Oct 2026).
"""

from __future__ import annotations

import importlib
import logging
import time
from collections.abc import Callable, Sequence
from typing import Any

from app.core import events
from app.core.config import get_settings

log = logging.getLogger(__name__)

JOB_TIMEOUT_S = 900
# Failed jobs keep their arguments in Redis (for retry and inspection) this long, not RQ's 1 year.
JOB_FAILURE_TTL_S = 7 * 24 * 3600


def job_name(fn: Callable[..., Any]) -> str:
    return f"{fn.__module__}.{fn.__qualname__}"


def run_job(name: str, args: Sequence[Any], kwargs: dict[str, Any]) -> Any:
    """Worker entry point: import ``name``, call it, and record the outcome and duration."""
    module, _, attr = name.rpartition(".")
    fn = getattr(importlib.import_module(module), attr)
    start = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
    except Exception:
        events.record_job(name, "failed", time.perf_counter() - start)
        raise
    events.record_job(name, "succeeded", time.perf_counter() - start)
    return result


def enqueue(
    fn: Callable[..., Any],
    *args: Any,
    retry_intervals: Sequence[int] = (),
    **kwargs: Any,
) -> str | None:
    """Run ``fn`` (a module-level function taking only JSON-safe args) in the background.

    Job functions open their own DB session; never pass ORM objects or sessions.
    ``retry_intervals`` (seconds) retries a failed RQ job once per entry; the worker must run with
    its scheduler (``python -m app.cli.worker`` does).
    """
    s = get_settings()
    name = job_name(fn)
    if s.job_mode == "sync":
        run_job(name, args, kwargs)
        return None
    import redis
    from rq import Queue, Retry

    q = Queue(s.job_queue_name, connection=redis.Redis.from_url(s.redis_url))
    job = q.enqueue_call(
        run_job,
        args=(name, list(args), kwargs),
        timeout=JOB_TIMEOUT_S,
        failure_ttl=JOB_FAILURE_TTL_S,
        description=name,
        retry=Retry(max=len(retry_intervals), interval=list(retry_intervals)) if retry_intervals else None,
    )
    return str(job.id)
