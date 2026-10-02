"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import hmac
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.db import get_engine
from app.core.errors import NotFound, Unauthorized, install_error_handlers
from app.core.observability import (
    REQUEST_ID_HEADER,
    configure_logging,
    incoming_request_id,
    metrics,
    request_id_var,
    runtime_metrics,
)
from app.models.rls import POLICY_NAME, RLS_TABLES

access_log = logging.getLogger("app.access")
admission_log = logging.getLogger("app.admission")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",
}


def rls_enforced() -> bool:
    """True when the current DB role is subject to the tree-isolation policies (ADR-0002 §7)."""
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT r.rolsuper OR r.rolbypassrls, "
                "EXISTS (SELECT 1 FROM pg_tables t WHERE t.tablename = 'person' AND t.tableowner = current_user), "
                "(SELECT count(*) FROM pg_policies p WHERE p.policyname = :policy) "
                "FROM pg_roles r WHERE r.rolname = current_user"
            ),
            {"policy": POLICY_NAME},
        ).one()
    bypasses, owns, policies = row
    return not bypasses and not owns and policies >= len(RLS_TABLES)


def readiness(settings: Settings) -> tuple[bool, dict[str, str]]:
    checks: dict[str, str] = {}
    ok = True
    try:
        with get_engine().connect() as conn:
            conn.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception:
        return False, {"database": "unavailable"}
    enforced = rls_enforced()
    checks["rls"] = "enforced" if enforced else "bypassed"
    if not enforced and settings.env == "production":
        ok = False  # never serve production traffic without the second isolation barrier
    if settings.job_mode == "rq" or settings.rate_limit_backend == "redis":
        try:
            import redis

            redis.Redis.from_url(settings.redis_url, socket_timeout=2).ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unavailable"
            ok = False
    return ok, checks


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    app = FastAPI(
        title="Vanshavali API",
        version="0.1.0",
        description="Privacy-first Indian family heritage platform. All tree data is authorised server-side.",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=None,
    )
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", settings.csrf_header_name],
    )

    limit = settings.max_inflight_requests or (settings.db_pool_size + settings.db_max_overflow)
    slots = asyncio.Semaphore(limit)
    exempt = {
        f"{settings.api_prefix}/health",
        f"{settings.api_prefix}/health/ready",
        f"{settings.api_prefix}/metrics",
    }

    @app.middleware("http")
    async def admission(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Bound in-progress API work per worker (load test, Oct 2026).

        Past capacity, unbounded admission made every request queue for a thread and a database
        connection, so throughput collapsed and clients waited up to a minute. Shedding the excess
        early keeps the admitted requests fast and tells clients to retry.
        """
        path = request.url.path
        if not path.startswith(settings.api_prefix) or path in exempt:
            return await call_next(request)
        try:
            await asyncio.wait_for(slots.acquire(), timeout=settings.admission_wait_s)
        except TimeoutError:
            admission_log.warning("admission limit (%d in progress) reached; shedding request", limit)
            metrics.inc_shed()
            return JSONResponse(
                status_code=503,
                headers={"Retry-After": "2"},
                content={
                    "error": {
                        "code": "server_busy",
                        "message": "The service is busy. Please try again in a moment.",
                        "details": None,
                    }
                },
            )
        try:
            return await call_next(request)
        finally:
            slots.release()

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = incoming_request_id(request.headers.get(REQUEST_ID_HEADER))
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers[REQUEST_ID_HEADER] = rid
            return response
        finally:
            elapsed = time.perf_counter() - start
            route = getattr(request.scope.get("route"), "path", None) or "unmatched"
            if route != "unmatched" and not route.startswith(settings.api_prefix):
                route = settings.api_prefix + route  # routes of the included api_router omit its prefix
            metrics.observe(request.method, route, status, elapsed)
            access_log.info(
                "%s %s %s",
                request.method,
                route,
                status,
                extra={
                    "method": request.method,
                    "route": route,
                    "status": status,
                    "duration_ms": round(elapsed * 1000, 1),
                },
            )
            request_id_var.reset(token)

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            if k == "Content-Security-Policy" and request.url.path.endswith("/docs"):
                continue
            response.headers.setdefault(k, v)
        if settings.cookie_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get(f"{settings.api_prefix}/health", tags=["platform"])
    def health() -> dict[str, str]:
        """Liveness: the process is serving requests. Does not touch dependencies."""
        return {"status": "ok"}

    @app.get(f"{settings.api_prefix}/health/ready", tags=["platform"])
    def ready() -> JSONResponse:
        """Readiness: database reachable, RLS in force (required in production), Redis if used."""
        ok, checks = readiness(settings)
        body: dict[str, Any] = {"status": "ok" if ok else "unavailable", "checks": checks}
        return JSONResponse(body, status_code=200 if ok else 503)

    @app.get(f"{settings.api_prefix}/metrics", include_in_schema=False)
    def prometheus(request: Request) -> Response:
        expected = settings.metrics_token
        given = request.headers.get("authorization", "")
        if not expected:
            raise NotFound()
        if not hmac.compare_digest(given.encode(), f"Bearer {expected}".encode()):
            raise Unauthorized()
        body = metrics.render() + runtime_metrics(settings)
        return PlainTextResponse(body, media_type="text/plain; version=0.0.4")

    return app


app = create_app()
