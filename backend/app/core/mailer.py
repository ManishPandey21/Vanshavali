"""Outbound email (ADR-0005): console, file or SMTP backend, always sent through the job queue.

Messages are plain text plus a simple HTML alternative. No images, tracking pixels or rewritten links.

* ``console`` logs the message. Outside development, anything passed as ``sensitive`` (and any
  token-looking link segment) is redacted from the log line, so logs never carry live tokens.
* ``file`` writes ``<name>.eml`` and ``<name>.json`` into ``VSH_MAIL_FILE_DIR`` (tests and E2E read these).
* ``smtp`` delivers with :mod:`smtplib` using STARTTLS. Production refuses the other two backends.
"""

from __future__ import annotations

import json
import logging
import os
import re
import smtplib
import ssl
import time
import uuid
from collections.abc import Iterable
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path
from typing import Any

from app.core import events
from app.core.config import get_settings
from app.core.jobs import enqueue

log = logging.getLogger("app.mail")

REDACTED = "[redacted]"
# A failed delivery (SMTP outage, auth failure) is retried by the worker after these delays (seconds).
# The last attempt is about 21 minutes after the first; verification links stay valid for 48 hours.
RETRY_INTERVALS_S = (60, 300, 900)
# Any long URL-safe token (our tokens are 43 chars) in a path segment or query value.
_TOKEN_RE = re.compile(r"(?:(?<=[/=#])|(?<=%23))[A-Za-z0-9_-]{32,}")


def redact(text: str, sensitive: Iterable[str] = ()) -> str:
    for secret in sensitive:
        if secret:
            text = text.replace(secret, REDACTED)
    return _TOKEN_RE.sub(REDACTED, text)


def send(
    to: str, subject: str, text: str, html: str, *, sensitive: Iterable[str] = (), kind: str = "generic"
) -> None:
    """Queue one email. ``sensitive`` values (e.g. tokens) are redacted from any log output.

    A delivery failure never fails the caller's request: auth endpoints must answer identically
    whether or not an email was sent (no account enumeration). In RQ mode the job itself fails and
    can be retried; in sync mode the failure is logged without the message body.
    """
    payload = {
        "to": to,
        "subject": subject,
        "text": text,
        "html": html,
        "sensitive": list(sensitive),
        "kind": kind,
    }
    try:
        enqueue(deliver, payload, retry_intervals=RETRY_INTERVALS_S)
    except Exception as exc:
        events.record("mail_send_failed")
        log.error("email (%s) to=%s could not be sent: %s", kind, mask_address(to), type(exc).__name__)


def mask_address(address: str) -> str:
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def build_message(payload: dict[str, Any]) -> EmailMessage:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.mail_from
    msg["To"] = payload["to"]
    msg["Subject"] = payload["subject"]
    msg["Date"] = formatdate(localtime=False, usegmt=True)
    domain = parseaddr(s.mail_from)[1].partition("@")[2] or "localhost"
    msg["Message-ID"] = make_msgid(domain=domain)
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(payload["text"])
    msg.add_alternative(payload["html"], subtype="html")
    return msg


def deliver(payload: dict[str, Any]) -> None:
    """Job entry point: build and hand the message to the configured backend."""
    backend = get_settings().mail_backend
    msg = build_message(payload)
    try:
        if backend == "smtp":
            _deliver_smtp(msg)
        elif backend == "file":
            _deliver_file(msg, payload)
        else:
            _deliver_console(payload)
    except Exception as exc:
        # Type only: SMTP replies can quote the message or the recipient. The job fails and is retried.
        events.record("mail_delivery_failed")
        log.warning(
            "email (%s) to=%s delivery attempt failed: %s",
            payload.get("kind"),
            mask_address(payload["to"]),
            type(exc).__name__,
        )
        raise


def _deliver_console(payload: dict[str, Any]) -> None:
    s = get_settings()
    body = payload["text"]
    to = payload["to"]
    if s.env != "development":
        body = redact(body, payload.get("sensitive", ()))
        to = mask_address(to)
    log.info("email (%s) to=%s subject=%r\n%s", payload.get("kind"), to, payload["subject"], body)


def _deliver_file(msg: EmailMessage, payload: dict[str, Any]) -> None:
    out = Path(get_settings().mail_file_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = f"{time.time_ns():020d}-{uuid.uuid4().hex[:8]}"
    (out / f"{name}.eml").write_bytes(bytes(msg))
    record = {
        "to": payload["to"],
        "subject": payload["subject"],
        "text": payload["text"],
        "html": payload["html"],
        "kind": payload.get("kind"),
        "sent_at": msg["Date"],
    }
    # write-then-rename so readers (E2E polling the directory) never see a partial file
    tmp = out / f".{name}.json.tmp"
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, out / f"{name}.json")


def _deliver_smtp(msg: EmailMessage) -> None:
    s = get_settings()
    if not s.smtp_host:
        raise RuntimeError("VSH_SMTP_HOST is not configured")
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds) as smtp:
        smtp.ehlo()
        if s.smtp_starttls:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password or "")
        smtp.send_message(msg)
