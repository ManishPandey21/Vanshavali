"""Request IDs, privacy-safe access logs, metrics, liveness/readiness and the statement timeout."""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.observability import JsonFormatter, Metrics, request_id_var
from app.main import readiness


def test_request_id_is_minted_or_propagated(client):
    r = client.get("/health")
    minted = r.headers["x-request-id"]
    assert len(minted) == 32
    upstream = "lb-" + uuid.uuid4().hex
    assert client.get("/health", headers={"X-Request-ID": upstream}).headers["x-request-id"] == upstream
    # header injection / junk is replaced, never echoed
    bad = client.get("/health", headers={"X-Request-ID": "x y<script>"}).headers["x-request-id"]
    assert bad != "x y<script>" and len(bad) == 32


def test_access_log_uses_route_template_not_raw_path_or_query(owner, tree, caplog):
    t = tree["id"]
    with caplog.at_level(logging.INFO, logger="app.access"):
        owner.get(f"/trees/{t}/people", params={"q": "Kamala", "token": "s3cr3t-signed-token"})
    recs = [r for r in caplog.records if r.name == "app.access"]
    assert recs, "no access log line"
    line = recs[-1]
    assert line.route == "/api/v1/trees/{tree_id}/people"  # type: ignore[attr-defined]
    assert line.status == 200 and line.method == "GET"  # type: ignore[attr-defined]
    text_ = line.getMessage() + str(line.__dict__)
    assert t not in text_ and "s3cr3t" not in text_ and "Kamala" not in text_


def test_json_formatter_includes_request_id_and_extras():
    token = request_id_var.set("req-12345678")
    try:
        rec = logging.LogRecord("app.x", logging.INFO, __file__, 1, "hello %s", ("world",), None)
        rec.request_id = request_id_var.get()
        rec.route = "/api/v1/health"
        out = json.loads(JsonFormatter().format(rec))
    finally:
        request_id_var.reset(token)
    assert out["msg"] == "hello world" and out["request_id"] == "req-12345678"
    assert out["route"] == "/api/v1/health" and out["level"] == "INFO" and out["ts"].endswith("Z")


def test_metrics_endpoint_requires_configured_token(client, monkeypatch):
    assert client.get("/metrics").status_code == 404  # disabled by default
    monkeypatch.setattr(get_settings(), "metrics_token", "scrape-token-123")
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer nope"}).status_code == 401
    client.get("/health")
    r = client.get("/metrics", headers={"Authorization": "Bearer scrape-token-123"})
    assert r.status_code == 200
    assert 'vsh_http_requests_total{method="GET",route="/api/v1/health",status="2xx"}' in r.text
    assert "vsh_http_request_duration_seconds_bucket" in r.text


def test_metrics_render_is_valid_and_escaped():
    m = Metrics()
    m.observe("GET", '/a"b', 200, 0.003)
    m.observe("GET", '/a"b', 503, 7.0)
    out = m.render()
    assert 'route="/a\\"b"' in out
    assert 'vsh_http_request_duration_seconds_bucket{method="GET",route="/a\\"b",le="+Inf"} 2' in out
    assert 'vsh_http_request_duration_seconds_bucket{method="GET",route="/a\\"b",le="0.005"} 1' in out
    assert 'status="5xx"} 1' in out


def test_liveness_and_readiness(client):
    assert client.get("/health").json() == {"status": "ok"}
    r = client.get("/health/ready")
    assert r.status_code == 200
    # the test suite connects as the restricted role, so the second barrier is reported in force
    assert r.json() == {"status": "ok", "checks": {"database": "ok", "rls": "enforced"}}


def test_readiness_fails_in_production_when_rls_is_bypassed(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "rls_enforced", lambda: False)
    dev = get_settings().model_copy(update={"env": "development"})
    prod = get_settings().model_copy(update={"env": "production"})
    assert readiness(dev) == (True, {"database": "ok", "rls": "bypassed"})
    assert readiness(prod) == (False, {"database": "ok", "rls": "bypassed"})


def test_owner_connection_is_reported_as_bypassing_rls():
    from sqlalchemy import create_engine

    import app.main as main
    from tests.conftest import OWNER_URL

    eng = create_engine(OWNER_URL)
    try:
        orig = main.get_engine
        main.get_engine = lambda: eng  # type: ignore[assignment]
        try:
            assert main.rls_enforced() is False
        finally:
            main.get_engine = orig
    finally:
        eng.dispose()
    assert main.rls_enforced() is True


def test_statement_timeout_applies_to_app_connections():
    with get_engine().connect() as conn:
        assert conn.execute(text("SHOW statement_timeout")).scalar() == "15s"
