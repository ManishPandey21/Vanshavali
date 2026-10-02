"""Background worker (RQ): documents (scan, previews, OCR, extraction) and email delivery.

    python -m app.cli.worker [--burst] [--queue NAME ...]

``--queue render`` serves the animated-export queue (``VSH_RENDER_QUEUE_NAME``); run it as its own
worker on a host with Node, Chromium and the renderer bundle (docs/architecture/remotion-rendering.md).

Use this instead of the bare ``rq worker`` command:

* logs go through the app's formatter (``VSH_LOG_FORMAT=json`` gives one JSON object per line);
* the RQ scheduler runs in the worker, which failed-email retries need (``mailer.RETRY_INTERVALS_S``);
* job descriptions are never logged with their arguments (they can carry email addresses).
"""

from __future__ import annotations

import argparse

from app.core.config import get_settings
from app.core.observability import configure_logging


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--burst", action="store_true", help="process the queue, then exit (tests, drills)")
    ap.add_argument(
        "--queue",
        action="append",
        default=None,
        help="queue to serve: 'default' (documents, email, reminders) or 'render'; repeatable",
    )
    args = ap.parse_args(argv)

    s = get_settings()
    configure_logging(s)
    import redis
    from rq import Queue, Worker

    conn = redis.Redis.from_url(s.redis_url)
    names = {"default": s.job_queue_name, "render": s.render_queue_name}
    queues = [names.get(q, q) for q in (args.queue or ["default"])]
    worker = Worker(
        [Queue(q, connection=conn) for q in queues],
        connection=conn,
        log_job_description=False,
    )
    # RQ adds its own log handler only when none is configured, so the root handler above is used.
    ok = worker.work(burst=args.burst, with_scheduler=True, logging_level=s.log_level.upper())
    return 0 if ok or not args.burst else 1


if __name__ == "__main__":
    raise SystemExit(main())
