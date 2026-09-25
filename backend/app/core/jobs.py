"""Background jobs: inline (tests/single-process dev) or Redis + RQ (production)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.core.config import get_settings

log = logging.getLogger(__name__)


def enqueue(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> str | None:
    """Run ``fn`` (a module-level function taking only JSON-safe args) in the background.

    Job functions open their own DB session; never pass ORM objects or sessions.
    """
    s = get_settings()
    if s.job_mode == "sync":
        fn(*args, **kwargs)
        return None
    import redis
    from rq import Queue

    q = Queue(s.job_queue_name, connection=redis.Redis.from_url(s.redis_url))
    job = q.enqueue(fn, *args, **kwargs, job_timeout=900)
    return str(job.id)
