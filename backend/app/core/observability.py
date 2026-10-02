"""Operational telemetry: request IDs, structured logs, Prometheus metrics, readiness checks.

Privacy rules (PRS §34): logs carry the *route template* (``/trees/{tree_id}/people/{person_id}``),
never the raw path or query string. Signed download tokens travel in query strings, and paths can
carry public slugs. No request or response bodies, cookies or headers other than the request ID are
logged. Uvicorn's own access log is switched off for the same reason.
"""

from __future__ import annotations

import bisect
import json
import logging
import re
import sys
import threading
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar
from typing import Any

from app.core.config import Settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
REQUEST_ID_HEADER = "X-Request-ID"

# Fields that may be attached with ``log.info(..., extra={...})`` and are emitted as JSON keys.
_EXTRA_FIELDS = ("method", "route", "status", "duration_ms", "job", "tree_id")


def incoming_request_id(value: str | None) -> str:
    """Accept a well-formed upstream request ID (load balancer / proxy), otherwise mint one."""
    if value and _REQUEST_ID_RE.match(value):
        return value
    return uuid.uuid4().hex


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = getattr(record, "request_id", None)
        if rid:
            out["request_id"] = rid
        for key in _EXTRA_FIELDS:
            if hasattr(record, key):
                out[key] = getattr(record, key)
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str, ensure_ascii=False)


JsonFormatter.converter = time.gmtime  # type: ignore[assignment]

_configured = False


def configure_logging(settings: Settings) -> None:
    """Install one stdout handler on the root logger (idempotent)."""
    global _configured
    if _configured:
        return
    _configured = True
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    if settings.log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")
        )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    # Raw access lines would include query strings (signed download tokens): use ours instead.
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True


# ---------------------------------------------------------------- metrics
_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class Metrics:
    """A tiny in-process Prometheus registry (per process; scrape each replica)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.started = time.time()
        self.requests: dict[tuple[str, str, str], int] = defaultdict(int)
        self.hist: dict[tuple[str, str], list[int]] = {}
        self.hist_sum: dict[tuple[str, str], float] = defaultdict(float)
        self.shed = 0

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self.requests[(method, route, f"{status // 100}xx")] += 1
            key = (method, route)
            counts = self.hist.setdefault(key, [0] * (len(_BUCKETS) + 1))
            counts[bisect.bisect_left(_BUCKETS, seconds)] += 1
            self.hist_sum[key] += seconds

    def inc_shed(self) -> None:
        with self._lock:
            self.shed += 1

    def render(self) -> str:
        def lbl(**kv: str) -> str:
            return "{" + ",".join(f'{k}="{_escape(v)}"' for k, v in kv.items()) + "}"

        lines = [
            "# HELP vsh_http_requests_total HTTP requests by route template and status class.",
            "# TYPE vsh_http_requests_total counter",
        ]
        with self._lock:
            for (m, r, s), n in sorted(self.requests.items()):
                lines.append(f"vsh_http_requests_total{lbl(method=m, route=r, status=s)} {n}")
            lines += [
                "# HELP vsh_http_request_duration_seconds Request latency by route template.",
                "# TYPE vsh_http_request_duration_seconds histogram",
            ]
            for (m, r), counts in sorted(self.hist.items()):
                cum = 0
                for le, c in zip([*map(str, _BUCKETS), "+Inf"], counts, strict=True):
                    cum += c
                    lines.append(
                        f"vsh_http_request_duration_seconds_bucket{lbl(method=m, route=r, le=le)} {cum}"
                    )
                lines.append(
                    f"vsh_http_request_duration_seconds_sum{lbl(method=m, route=r)} {self.hist_sum[(m, r)]:.6f}"
                )
                lines.append(f"vsh_http_request_duration_seconds_count{lbl(method=m, route=r)} {cum}")
        lines += [
            "# HELP vsh_process_start_time_seconds Unix time the process started.",
            "# TYPE vsh_process_start_time_seconds gauge",
            f"vsh_process_start_time_seconds {self.started:.0f}",
        ]
        return "\n".join(lines) + "\n"


metrics = Metrics()


def _job_label(name: str) -> str:
    # app.modules.documents.processing.process_document -> documents.process_document
    parts = name.split(".")
    return ".".join(p for p in (parts[2] if len(parts) > 3 else "", parts[-1]) if p)


def runtime_metrics(settings: Settings) -> str:
    """Gauges read at scrape time: DB pool, job queue, and the shared event counters.

    Pool gauges describe this process. Queue gauges and event/job counters are cluster-wide when jobs
    run through RQ (every replica reports the same values; aggregate with ``max``).
    """
    from app.core import events
    from app.core.db import get_engine

    lines: list[str] = []

    def gauge(name: str, help_: str, value: float, kind: str = "gauge") -> None:
        lines.extend([f"# HELP {name} {help_}", f"# TYPE {name} {kind}", f"{name} {value:g}"])

    try:
        with get_engine().connect() as db:
            db.exec_driver_sql("select 1")
        db_up = 1
    except Exception:
        db_up = 0
    gauge("vsh_db_up", "1 if this process reached the database during this scrape.", db_up)
    pool: Any = get_engine().pool
    try:
        gauge("vsh_db_pool_size", "Configured connections per process (excluding overflow).", pool.size())
        gauge("vsh_db_pool_checked_out", "Connections in use in this process.", pool.checkedout())
        gauge(
            "vsh_db_pool_overflow", "Overflow connections open beyond the pool size.", max(pool.overflow(), 0)
        )
    except AttributeError:  # pragma: no cover - non-queue pools (tests with NullPool)
        pass
    gauge(
        "vsh_requests_shed_total", "API requests refused by admission control (503).", metrics.shed, "counter"
    )

    if settings.job_mode == "rq":
        try:
            import redis
            from rq import Queue, Worker
            from rq.registry import FailedJobRegistry, ScheduledJobRegistry, StartedJobRegistry

            conn = redis.Redis.from_url(settings.redis_url, socket_timeout=2)
            q = Queue(settings.job_queue_name, connection=conn)
            gauge("vsh_jobs_queued", "Jobs waiting in the queue.", q.count)
            gauge("vsh_jobs_running", "Jobs being processed.", StartedJobRegistry(queue=q).count)
            gauge(
                "vsh_jobs_scheduled",
                "Jobs waiting for a retry or a scheduled time.",
                ScheduledJobRegistry(queue=q).count,
            )
            gauge(
                "vsh_jobs_failed",
                "Jobs in the failed registry (kept 7 days).",
                FailedJobRegistry(queue=q).count,
            )
            gauge("vsh_workers", "Live background workers.", Worker.count(queue=q))
            gauge("vsh_queue_up", "1 if the job queue (Redis) answered this scrape.", 1)
        except Exception:
            gauge("vsh_queue_up", "1 if the job queue (Redis) answered this scrape.", 0)

    snap = events.snapshot()
    ev = sorted((k.split("|", 1)[1], v) for k, v in snap.items() if k.startswith("event|"))
    lines += [
        "# HELP vsh_events_total Operational failures by kind (mail, storage, OCR, import).",
        "# TYPE vsh_events_total counter",
    ]
    lines += [f'vsh_events_total{{event="{_escape(e)}"}} {v:g}' for e, v in ev]
    runs = sorted((k.split("|")[1:], v) for k, v in snap.items() if k.startswith("job|"))
    lines += [
        "# HELP vsh_job_runs_total Background job runs by job and outcome (each retry counts).",
        "# TYPE vsh_job_runs_total counter",
    ]
    lines += [
        f'vsh_job_runs_total{{job="{_escape(_job_label(j))}",outcome="{_escape(o)}"}} {v:g}'
        for (j, o), v in runs
    ]
    lines += [
        "# HELP vsh_job_duration_seconds Background job run time (sum and count; mean = sum / count).",
        "# TYPE vsh_job_duration_seconds summary",
    ]
    for k, v in sorted(snap.items()):
        if k.startswith("jobsec|"):
            j = k.split("|", 1)[1]
            lbl = f'{{job="{_escape(_job_label(j))}"}}'
            lines.append(f"vsh_job_duration_seconds_sum{lbl} {v:.6f}")
            lines.append(f"vsh_job_duration_seconds_count{lbl} {snap.get(f'jobcount|{j}', 0):g}")
    return "\n".join(lines) + "\n"
