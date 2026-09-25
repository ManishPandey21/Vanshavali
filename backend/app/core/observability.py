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

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self.requests[(method, route, f"{status // 100}xx")] += 1
            key = (method, route)
            counts = self.hist.setdefault(key, [0] * (len(_BUCKETS) + 1))
            counts[bisect.bisect_left(_BUCKETS, seconds)] += 1
            self.hist_sum[key] += seconds

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
