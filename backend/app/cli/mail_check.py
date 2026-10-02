"""Check the outbound email configuration (docs/operations/email-runbook.md).

    python -m app.cli.mail_check                 # connect, STARTTLS, log in; send nothing
    python -m app.cli.mail_check --send-to ADDR  # also deliver one test message, synchronously

Runs with the same environment as the API and worker. Prints the settings in use with the password
masked, then each step with its outcome. Exit status 0 means every step passed. The test message
contains no account data and no links.
"""

from __future__ import annotations

import argparse
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from app.core.config import get_settings


def _step(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{': ' + detail if detail else ''}")
    return ok


def _error(exc: BaseException) -> str:
    # SMTP replies are useful here (e.g. "535 authentication failed") and never contain the password.
    if isinstance(exc, smtplib.SMTPResponseException):
        err = exc.smtp_error
        text = err.decode(errors="replace") if isinstance(err, bytes) else str(err)
        return f"{type(exc).__name__} {exc.smtp_code} {text[:200]}"
    return f"{type(exc).__name__}: {str(exc)[:200]}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--send-to", metavar="ADDR", help="deliver one test message to this address")
    args = ap.parse_args(argv)
    s = get_settings()
    print(
        f"backend={s.mail_backend} host={s.smtp_host} port={s.smtp_port} starttls={s.smtp_starttls} "
        f"user={s.smtp_user or '-'} password={'set' if s.smtp_password else 'not set'} "
        f"from={s.mail_from} timeout={s.smtp_timeout_seconds}s"
    )
    if s.mail_backend != "smtp":
        _step("backend", True, f"{s.mail_backend}: nothing to connect to")
        return 0
    if not _step("from address", "@" in parseaddr(s.mail_from)[1], parseaddr(s.mail_from)[1]):
        return 1
    if not s.smtp_host:
        _step("host", False, "VSH_SMTP_HOST is not set")
        return 1
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds) as smtp:
            _step("connect", True, f"{s.smtp_host}:{s.smtp_port}")
            smtp.ehlo()
            if s.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                _step("STARTTLS", True, "certificate verified")
            else:
                print(
                    "[WARN] STARTTLS disabled: credentials and mail travel in clear (refused in production)"
                )
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password or "")
                _step("login", True, s.smtp_user)
            if args.send_to:
                msg = EmailMessage()
                msg["From"] = s.mail_from
                msg["To"] = args.send_to
                msg["Subject"] = "Vanshavali email check"
                msg["Date"] = formatdate(usegmt=True)
                msg["Message-ID"] = make_msgid(domain=parseaddr(s.mail_from)[1].partition("@")[2] or None)
                msg["Auto-Submitted"] = "auto-generated"
                msg.set_content("This is a test message from the Vanshavali email check. No action needed.")
                refused = smtp.send_message(msg)
                _step("send", not refused, f"accepted for {args.send_to}; Message-ID {msg['Message-ID']}")
                if refused:
                    return 1
    except Exception as exc:
        _step("SMTP", False, _error(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
