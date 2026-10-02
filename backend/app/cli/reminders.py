"""Reminder scheduler (ADR-0016).

    python -m app.cli.reminders tick          # once (cron every 5 minutes)
    python -m app.cli.reminders tick --loop   # every --interval seconds (a small sidecar process)

Each tick materialises due deliveries (idempotently) and enqueues them on the job queue; retries
that are due and deliveries whose job was lost are enqueued again. Safe to run on several hosts.
"""

from __future__ import annotations

import argparse
import logging
import time

from app.core.config import get_settings
from app.core.observability import configure_logging

log = logging.getLogger("app.reminders")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tick", help="run the scheduler")
    t.add_argument("--loop", action="store_true")
    t.add_argument("--interval", type=int, default=300)
    args = ap.parse_args(argv)
    configure_logging(get_settings())
    from app.modules.notifications.service import tick

    while True:
        res = tick()
        log.info(
            "reminder tick: trees=%d reminders=%d created=%d enqueued=%d",
            res.trees,
            res.reminders,
            res.created,
            res.enqueued,
        )
        if not args.loop:
            return 0
        time.sleep(max(30, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
