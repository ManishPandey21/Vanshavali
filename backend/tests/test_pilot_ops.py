"""Pilot deployment audit (Oct 2026): start-up guards, job hygiene, email, storage errors, metrics."""

from __future__ import annotations

import logging
import smtplib
from typing import Any

import pytest
from botocore.exceptions import EndpointConnectionError
from fastapi.testclient import TestClient

from app.core import events, jobs, mailer
from app.core.config import Settings, get_settings, unsafe_forwarded_allow_ips
from app.core.storage import StorageError
from app.main import create_app
from app.modules.identity import emails

_PROD_OK: dict[str, Any] = {
    "env": "production",
    "scanner": "clamd",
    "standard_data_key": "c3RhbmRhcmQta2V5LTMyLWJ5dGVzLXByb2QtLS0tLS0=",
    "vault_data_key": "dmF1bHQta2V5LTMyLWJ5dGVzLXByb2R1Y3Rpb24tLS0=",
    "signing_key": "x" * 48,
    "mail_backend": "smtp",
    "smtp_host": "smtp.example.net",
    "mail_from": "Vanshavali <no-reply@example.org>",
    "cookie_secure": True,
    "public_base_url": "https://pilot.example.org",
    "cors_origins": ["https://pilot.example.org"],
}


def _prod(monkeypatch: pytest.MonkeyPatch, forwarded: str = "172.28.0.20", **overrides: Any) -> Settings:
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", forwarded)
    return Settings(**{**_PROD_OK, **overrides})


# ------------------------------------------------------------------ trusted proxies (T30)
@pytest.mark.parametrize(
    ("value", "bad"),
    [
        ("*", ["*"]),
        ("172.28.0.20,*", ["*"]),
        ("0.0.0.0/0", ["0.0.0.0/0"]),
        ("::/0", ["::/0"]),
        ("172.28.0.20", []),
        ("10.0.0.0/16, 127.0.0.1", []),
        ("/run/proxy.sock", []),
    ],
)
def test_unsafe_forwarded_allow_ips_are_detected(value: str, bad: list[str]) -> None:
    assert unsafe_forwarded_allow_ips(value) == bad


def test_production_accepts_explicit_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _prod(monkeypatch).forwarded_allow_ips == "172.28.0.20"


@pytest.mark.parametrize("value", ["*", "172.28.0.20,*", "0.0.0.0/0"])
def test_production_refuses_wildcard_proxy_trust(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    with pytest.raises(ValueError, match="FORWARDED_ALLOW_IPS"):
        _prod(monkeypatch, forwarded=value)


def test_production_warns_when_only_loopback_is_trusted(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        _prod(monkeypatch, forwarded="127.0.0.1,::1")
    assert "per-IP rate limits apply to all users together" in caplog.text


def test_development_default_trusts_loopback_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
    assert Settings().forwarded_allow_ips == "127.0.0.1"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"signing_key": "short-but-not-the-dev-key"}, "at least 32 characters"),
        ({"vault_data_key": "dG9vLXNob3J0"}, "32 bytes"),
        ({"cors_origins": ["*"]}, "VSH_CORS_ORIGINS"),
        ({"public_base_url": "http://pilot.example.org"}, "https"),
        ({"mail_from": "Vanshavali <no-reply@localhost>"}, "VSH_MAIL_FROM"),
    ],
)
def test_production_refuses_weak_settings(
    monkeypatch: pytest.MonkeyPatch, override: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _prod(monkeypatch, **override)


# ------------------------------------------------------------------ background jobs
@pytest.fixture
def rq_mode(monkeypatch: pytest.MonkeyPatch) -> Any:
    import fakeredis
    import redis

    server = fakeredis.FakeServer()
    monkeypatch.setattr(redis.Redis, "from_url", lambda *a, **k: fakeredis.FakeStrictRedis(server=server))
    monkeypatch.setattr(get_settings(), "job_mode", "rq")
    monkeypatch.setattr(events, "_redis", None)
    return fakeredis.FakeStrictRedis(server=server)


def test_email_jobs_do_not_carry_addresses_into_worker_logs(
    rq_mode: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from rq import Queue, SimpleWorker

    s = get_settings()
    emails.send_verification("ramesh.iyer@example.org", "Ramesh", "en", "T" * 43)
    q = Queue(s.job_queue_name, connection=rq_mode)
    (job,) = q.jobs
    assert job.description == "app.core.mailer.deliver"  # RQ's default is the call with its arguments
    assert job.retries_left == len(mailer.RETRY_INTERVALS_S)
    assert job.failure_ttl == jobs.JOB_FAILURE_TTL_S
    before = events.snapshot().get("job|app.core.mailer.deliver|succeeded", 0)
    with caplog.at_level(logging.INFO):
        SimpleWorker([q], connection=rq_mode).work(burst=True)
    assert "ramesh.iyer" not in caplog.text and "Confirm your email" not in caplog.text
    assert events.snapshot()["job|app.core.mailer.deliver|succeeded"] == before + 1


def test_failed_delivery_is_counted_retried_and_logged_without_content(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def refuse(*a: Any, **k: Any) -> None:
        raise smtplib.SMTPAuthenticationError(535, b"authentication failed")

    monkeypatch.setattr(mailer, "_deliver_file", refuse)
    before = events.snapshot()
    with caplog.at_level(logging.WARNING, logger="app.mail"):
        emails.send_password_reset("sita@example.org", "Sita", "en", "R" * 43)
    after = events.snapshot()
    for key in ("event|mail_delivery_failed", "event|mail_send_failed", "job|app.core.mailer.deliver|failed"):
        assert after.get(key, 0) == before.get(key, 0) + 1, key
    assert "SMTPAuthenticationError" in caplog.text
    assert "sita@" not in caplog.text and "R" * 43 not in caplog.text


def test_html_email_has_one_footer() -> None:
    _, _, html = emails._render("verify", "en", "Ramesh", "https://pilot.example.org/verify-email/x")
    assert html.count("you can ignore this email") == 1


# ------------------------------------------------------------------ storage outage
@pytest.mark.parametrize(
    "exc",
    [StorageError("object not found: TREE/key"), EndpointConnectionError(endpoint_url="https://s3.test")],
)
def test_storage_failures_are_a_structured_503(exc: Exception) -> None:
    app = create_app()

    @app.get("/__test/storage")
    def _boom() -> None:
        raise exc

    before = events.snapshot().get("event|storage_error", 0)
    r = TestClient(app, raise_server_exceptions=False).get("/__test/storage")
    assert r.status_code == 503 and r.json()["error"]["code"] == "storage_unavailable"
    assert "TREE/key" not in r.text and "s3.test" not in r.text
    assert events.snapshot()["event|storage_error"] == before + 1


# ------------------------------------------------------------------ import failures
def test_gedcom_staging_failure_is_counted_and_logs_no_file_content(
    owner: Any, tree: dict[str, Any], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from app.modules.gedcom import mapping

    def explode(result: Any) -> Any:
        line = "1 NAME Ramesh /" + "Secretname/"  # parser errors can quote lines of the file
        raise ValueError(f"{line} could not be mapped")

    monkeypatch.setattr(mapping, "stage", explode)
    before = events.snapshot().get("event|gedcom_import_failed", 0)
    gedcom = "0 HEAD\n1 GEDC\n2 VERS 5.5.1\n0 @I1@ INDI\n1 NAME Ramesh /Secretname/\n0 TRLR\n"
    with caplog.at_level(logging.ERROR):
        r = owner.post(
            f"/trees/{tree['id']}/imports", files={"file": ("f.ged", gedcom.encode(), "text/plain")}
        )
    assert r.status_code == 201 and r.json()["status"] == "failed"
    assert "ValueError" in caplog.text and "Secretname" not in caplog.text
    assert events.snapshot()["event|gedcom_import_failed"] == before + 1


# ------------------------------------------------------------------ metrics
def test_metrics_expose_pool_queue_and_failure_counters(
    rq_mode: Any, client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "metrics_token", "t0ken")
    events.record("mail_delivery_failed")
    events.record_job("app.modules.documents.processing.process_document", "succeeded", 1.5)
    body = client.get("/metrics", headers={"Authorization": "Bearer t0ken"}).text
    for line in (
        "vsh_db_up 1",
        f"vsh_db_pool_size {get_settings().db_pool_size}",
        "vsh_db_pool_checked_out ",
        "vsh_requests_shed_total ",
        "vsh_jobs_queued 0",
        "vsh_jobs_failed 0",
        "vsh_queue_up 1",
        'vsh_events_total{event="mail_delivery_failed"} 1',
        'vsh_job_runs_total{job="documents.process_document",outcome="succeeded"} 1',
        'vsh_job_duration_seconds_sum{job="documents.process_document"} 1.500000',
    ):
        assert line in body, line


def test_metrics_report_the_queue_down_without_failing(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import redis

    monkeypatch.setattr(get_settings(), "metrics_token", "t0ken")
    monkeypatch.setattr(get_settings(), "job_mode", "rq")
    monkeypatch.setattr(get_settings(), "redis_url", "redis://127.0.0.1:1/0")
    monkeypatch.setattr(events, "_redis", redis.Redis.from_url("redis://127.0.0.1:1/0", socket_timeout=0.2))
    r = client.get("/metrics", headers={"Authorization": "Bearer t0ken"})
    assert r.status_code == 200 and "vsh_queue_up 0" in r.text


# ------------------------------------------------------------------ mail check CLI
def test_mail_check_reports_steps_and_never_prints_the_password(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.cli import mail_check

    calls: list[str] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            calls.append(f"connect {host}:{port}")

        def __enter__(self) -> FakeSMTP:
            return self

        def __exit__(self, *a: Any) -> bool:
            return False

        def ehlo(self) -> None:
            pass

        def starttls(self, context: Any) -> None:
            calls.append("starttls")

        def login(self, user: str, password: str) -> None:
            calls.append(f"login {user}")

        def send_message(self, msg: Any) -> dict[str, Any]:
            calls.append(f"send {msg['To']}")
            return {}

    s = get_settings()
    for k, v in {
        "mail_backend": "smtp",
        "smtp_host": "smtp.example.net",
        "smtp_user": "apikey",
        "smtp_password": "sup3r-secret-pw",
        "mail_from": "Vanshavali <no-reply@example.org>",
    }.items():
        monkeypatch.setattr(s, k, v)
    monkeypatch.setattr(mail_check.smtplib, "SMTP", FakeSMTP)
    assert mail_check.main(["--send-to", "ops@example.org"]) == 0
    out = capsys.readouterr().out
    assert calls == ["connect smtp.example.net:587", "starttls", "login apikey", "send ops@example.org"]
    assert "sup3r-secret-pw" not in out and "password=set" in out
    assert out.count("[PASS]") == 5


def test_mail_check_fails_on_authentication_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app.cli import mail_check

    class RefusingSMTP:
        def __init__(self, *a: Any, **k: Any) -> None:
            raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Authentication credentials invalid")

    s = get_settings()
    monkeypatch.setattr(s, "mail_backend", "smtp")
    monkeypatch.setattr(s, "smtp_host", "smtp.example.net")
    monkeypatch.setattr(mail_check.smtplib, "SMTP", RefusingSMTP)
    assert mail_check.main([]) == 1
    assert "[FAIL] SMTP: SMTPAuthenticationError 535" in capsys.readouterr().out


# ------------------------------------------------------------------ commit before respond
def test_a_failed_commit_is_an_error_not_a_success(owner: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The request's transaction commits before the response is sent (pilot benchmark, Oct 2026).

    With FastAPI's default dependency scope the commit in ``get_db`` ran after the response had gone
    out: a client could be told 201 while the write was still uncommitted (an immediate follow-up on
    another replica got 404 "Import not found") or was lost entirely if the commit then failed.
    """
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    real_commit = Session.commit
    calls: list[str] = []

    def failing_commit(self: Session) -> None:
        calls.append("commit")
        raise OperationalError("COMMIT", {}, Exception("server closed the connection unexpectedly"))

    client = TestClient(owner.client.app, raise_server_exceptions=False, cookies=owner.client.cookies)
    monkeypatch.setattr(Session, "commit", failing_commit)
    r = client.post(
        f"{get_settings().api_prefix}/trees", json={"name": "Never committed"}, headers=owner._headers()
    )
    monkeypatch.setattr(Session, "commit", real_commit)
    assert calls, "the request did not commit"
    assert r.status_code >= 500, f"client was told {r.status_code} although the commit failed"
    names = [t["name"] for t in owner.get("/trees").json()]
    assert "Never committed" not in names
