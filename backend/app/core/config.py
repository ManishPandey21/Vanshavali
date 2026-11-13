"""Application settings (12-factor: everything from environment variables)."""

from __future__ import annotations

import base64
import binascii
import ipaddress
import logging
from email.utils import parseaddr
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Development-only keys. Production refuses to start with these (see validate_production).
_DEV_STANDARD_KEY = base64.b64encode(b"vanshavali-dev-standard-key-32b!").decode()
_DEV_VAULT_KEY = base64.b64encode(b"vanshavali-dev-vault-key-32bytes").decode()
_DEV_SIGNING_KEY = "vanshavali-dev-signing-key-change-me"

log = logging.getLogger(__name__)


def unsafe_forwarded_allow_ips(value: str) -> list[str]:
    """Entries of a FORWARDED_ALLOW_IPS list that would let any client choose its own IP.

    uvicorn trusts ``X-Forwarded-For`` from these peers. ``*`` or a /0 network means every client
    is "trusted", so the rate limits, audit IPs and session IPs become client-controlled (threat T30).
    """
    bad = []
    for entry in (e.strip() for e in value.split(",")):
        if not entry:
            continue
        if entry == "*":
            bad.append(entry)
            continue
        try:
            if ipaddress.ip_network(entry, strict=False).prefixlen == 0:
                bad.append(entry)
        except ValueError:
            continue  # a hostname or unix socket path: uvicorn matches it literally
    return bad


def _is_loopback_only(value: str) -> bool:
    entries = [e.strip() for e in value.split(",") if e.strip()]
    try:
        return bool(entries) and all(ipaddress.ip_network(e, strict=False).is_loopback for e in entries)
    except ValueError:
        return False


def _key_is_32_bytes(raw: str) -> bool:
    try:
        return len(base64.b64decode(raw, validate=True)) == 32
    except (binascii.Error, ValueError):
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VSH_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    app_name: str = "Vanshavali"
    api_prefix: str = "/api/v1"
    public_base_url: str = "http://localhost:3000"
    # Read by uvicorn itself (no VSH_ prefix): the reverse proxies whose X-Forwarded-For is trusted.
    # Mirrored here only so production can refuse an unsafe value at start-up.
    forwarded_allow_ips: str = Field(
        default="127.0.0.1", validation_alias=AliasChoices("FORWARDED_ALLOW_IPS")
    )

    database_url: str = "postgresql+psycopg://vanshavali:vanshavali@localhost:5432/vanshavali"
    redis_url: str = "redis://localhost:6379/0"
    # Anonymous 30-day landing visitor estimates; opt-in at deployment after privacy review.
    visitor_stats_enabled: bool = False
    # Per-statement timeout for API/worker connections (0 disables); protects against runaway queries.
    statement_timeout_ms: int = 15000
    # Connection pool per worker process. Keep workers x (size + overflow) under PostgreSQL's
    # max_connections (minus admin/migration headroom). When the pool is exhausted a request waits at
    # most db_pool_timeout_s, then gets a 503 with Retry-After instead of hanging (load test, Oct 2026).
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_s: float = 5.0
    # Admission control per worker: at most this many API requests in progress (0 = pool size +
    # overflow, so admitted requests never queue for a connection). Excess requests wait up to
    # admission_wait_s for a slot, then get a 503 with Retry-After. Health and metrics are exempt.
    max_inflight_requests: int = 0
    admission_wait_s: float = 1.0

    # Observability: "json" for log shippers (recommended in production), "text" for humans.
    log_format: Literal["json", "text"] = "text"
    log_level: str = "INFO"
    # Bearer token for GET /metrics (Prometheus). Empty = the endpoint answers 404.
    metrics_token: str = ""

    # Sessions / cookies
    session_cookie_name: str = "vsh_session"
    csrf_cookie_name: str = "vsh_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    cookie_secure: bool = False
    session_idle_days: int = 14
    session_absolute_days: int = 30
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Rate limiting
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    login_rate_limit_per_minute: int = 10
    # per-IP account registrations per minute (the per-email limit, 5/hour, is fixed)
    register_rate_limit_per_minute: int = 20
    # per-IP uses of emailed one-time tokens (verify email, confirm password reset) per minute;
    # raised only by the E2E harness, never in production
    token_rate_limit_per_minute: int = 30

    # Jobs
    job_mode: Literal["sync", "rq"] = "sync"
    job_queue_name: str = "vanshavali"

    # Storage
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = "./var/storage"
    # Soft-deleted documents stay restorable this long, then the maintenance purge removes them.
    document_purge_after_days: int = 30
    s3_endpoint_url: str | None = None
    s3_bucket: str = "vanshavali"
    s3_region: str = "ap-south-1"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    standard_data_key: str = _DEV_STANDARD_KEY
    vault_data_key: str = _DEV_VAULT_KEY
    signing_key: str = _DEV_SIGNING_KEY
    download_url_ttl_seconds: int = 300

    # Upload limits
    max_upload_bytes: int = 50 * 1024 * 1024
    # GEDCOM import packages (a .zip or GEDZIP .gdz with the .ged and its photos, ADR-0013)
    max_gedcom_package_bytes: int = 250 * 1024 * 1024
    max_pdf_pages: int = 300
    max_image_pixels: int = 80_000_000

    # Malware scanning
    scanner: Literal["clamd", "eicar_test"] = "eicar_test"
    clamd_host: str = "localhost"
    clamd_port: int = 3310

    # OCR
    ocr_enabled: bool = True
    # Master-data vocabularies (ADR-0018); false = endpoints answer 404 and the UI falls back to text
    masterdata_enabled: bool = True
    # Super Admin master-data console (ADR-0028 §7). Off until the go-live checklist records two
    # named administrators; while off, every /admin/master-data route answers 404.
    masterdata_console_enabled: bool = False
    # Platform capabilities need a session opened with password + TOTP within this many hours, and
    # every write a TOTP step-up within this many minutes (ADR-0028 §7).
    platform_session_mfa_max_age_hours: int = 12
    platform_step_up_max_age_minutes: int = 15
    # Role or shared mailboxes the capability CLI refuses (local part, before any "+tag"): a
    # capability belongs to one named person (ADR-0028 §7).
    platform_mailbox_denylist: list[str] = [
        "abuse",
        "account",
        "accounts",
        "admin",
        "administrator",
        "billing",
        "contact",
        "dev",
        "devops",
        "help",
        "helpdesk",
        "hello",
        "hostmaster",
        "info",
        "it",
        "mail",
        "noreply",
        "no-reply",
        "office",
        "ops",
        "postmaster",
        "root",
        "sales",
        "security",
        "support",
        "sysadmin",
        "team",
        "webmaster",
    ]
    # Indian geography reference data (ADR-0019); false = /geo answers 404, places stay free text
    geo_enabled: bool = True
    # Family calendar (ADR-0022). Lunar conversion and reminders stay off until the engine licence
    # review is signed off and a convention's golden panchang table passes (§8); even when true,
    # only conventions marked verified are offered.
    lunar_calendar_enabled: bool = False
    # JPL DE440s ephemeris (checked against its pinned SHA-256); fetched with
    # `python -m app.cli.calendar fetch-ephemeris`, baked into the image by the Dockerfile
    ephemeris_path: str = "var/ephemeris/de440s.bsp"
    tesseract_cmd: str = "tesseract"
    tesseract_languages: str = "eng+hin"

    # GEDCOM
    gedcom_ext_base_uri: str = "https://vanshavali.app/gedcom/ext/v1/"

    # Email (ADR-0005). console: log only (links shown in development only); file: write .eml/.json
    # into mail_file_dir (tests, E2E); smtp: deliver via SMTP with STARTTLS (required in production).
    mail_backend: Literal["console", "file", "smtp"] = "console"
    mail_file_dir: str = "./var/mail"
    mail_from: str = "Vanshavali <no-reply@localhost>"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    smtp_timeout_seconds: int = 20

    # Email tokens
    email_verify_ttl_hours: int = 48
    password_reset_ttl_minutes: int = 60

    # Sign in with Google (OpenID Connect, ADR-0012). Off unless both id and secret are set.
    google_client_id: str | None = None
    google_client_secret: str | None = None
    # Where Google sends the browser back; defaults to <public_base_url><api_prefix>/auth/google/callback
    # (the SPA origin proxies /api). Must match the URI registered in Google Cloud exactly.
    google_redirect_uri: str | None = None
    google_authorize_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    google_token_url: str = "https://oauth2.googleapis.com/token"  # noqa: S105 - endpoint URL, not a secret
    oidc_state_ttl_seconds: int = 600

    # Traversal limits
    max_traversal_depth: int = 25

    # Reminders and notifications (ADR-0016; docs/operations/notification-providers.md).
    # Email reminders use the mailer above. SMS / WhatsApp: "disabled" (not offered), "mock" (writes
    # JSON into notification_outbox_dir; tests, E2E and demos; refused in production) or a provider.
    sms_backend: Literal["disabled", "mock", "twilio"] = "disabled"
    whatsapp_backend: Literal["disabled", "mock", "twilio", "meta"] = "disabled"
    notification_outbox_dir: str = "./var/notifications"
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_sms_from: str | None = None  # E.164 number or messaging service SID
    twilio_whatsapp_from: str | None = None  # e.g. +14155238886 (sent as whatsapp:+...)
    twilio_api_base: str = "https://api.twilio.com"
    whatsapp_meta_token: str | None = None
    whatsapp_meta_phone_number_id: str | None = None
    whatsapp_meta_template: str = "family_reminder"  # approved template with one body parameter
    whatsapp_meta_template_language: str = "en"
    whatsapp_meta_api_base: str = "https://graph.facebook.com/v20.0"
    provider_timeout_seconds: int = 15
    # how far back the scheduler still delivers a missed reminder (scheduler downtime)
    reminder_grace_hours: int = 36

    # Animated exports (ADR-0017; docs/architecture/remotion-rendering.md). "disabled": the API
    # answers 503 render_unavailable; "stub": deterministic placeholder artifacts (tests); "remotion":
    # the Node renderer in renderer/ (needs Node 20+, Chromium and the built bundle).
    render_backend: Literal["disabled", "stub", "remotion"] = "disabled"
    render_queue_name: str = "vanshavali-render"
    renderer_dir: str = "../renderer"
    renderer_node: str = "node"
    renderer_browser_executable: str | None = None
    render_timeout_seconds: int = 600
    render_max_active_per_user: int = 3
    render_max_per_day_per_tree: int = 50
    render_max_payload_bytes: int = 8 * 1024 * 1024

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def google_callback_uri(self) -> str:
        return self.google_redirect_uri or f"{self.public_base_url}{self.api_prefix}/auth/google/callback"

    @model_validator(mode="after")
    def validate_production(self) -> Settings:
        if self.env == "production":
            problems = []
            if self.scanner != "clamd":
                problems.append("VSH_SCANNER must be 'clamd' in production")
            if self.standard_data_key == _DEV_STANDARD_KEY or self.vault_data_key == _DEV_VAULT_KEY:
                problems.append("data keys must be set from a secret manager in production")
            elif not (_key_is_32_bytes(self.standard_data_key) and _key_is_32_bytes(self.vault_data_key)):
                problems.append(
                    "VSH_STANDARD_DATA_KEY and VSH_VAULT_DATA_KEY must be 32 bytes, base64-encoded"
                )
            if self.signing_key == _DEV_SIGNING_KEY:
                problems.append("VSH_SIGNING_KEY must be set in production")
            elif len(self.signing_key) < 32:
                problems.append("VSH_SIGNING_KEY must be at least 32 characters")
            if bad := unsafe_forwarded_allow_ips(self.forwarded_allow_ips):
                problems.append(
                    f"FORWARDED_ALLOW_IPS must list only the reverse proxies in front of the API, not {bad}"
                )
            if "*" in self.cors_origins:
                problems.append("VSH_CORS_ORIGINS must list the real origin, not '*'")
            if not self.public_base_url.startswith("https://"):
                problems.append("VSH_PUBLIC_BASE_URL must use https in production")
            if self.mail_backend != "smtp":
                problems.append("VSH_MAIL_BACKEND must be 'smtp' in production")
            elif not self.smtp_host or not self.smtp_starttls:
                problems.append("VSH_SMTP_HOST must be set and STARTTLS enabled in production")
            if parseaddr(self.mail_from)[1].lower().endswith("@localhost"):
                problems.append("VSH_MAIL_FROM must be an address on your sending domain (SPF/DKIM)")
            if not self.cookie_secure:
                problems.append("VSH_COOKIE_SECURE must be true in production")
            if "mock" in (self.sms_backend, self.whatsapp_backend):
                problems.append("SMS/WhatsApp 'mock' backends are for tests and demos, not production")
            if self.render_backend == "stub":
                problems.append("VSH_RENDER_BACKEND=stub is for tests only")
            if self.google_enabled and not self.google_callback_uri.startswith("https://"):
                problems.append("the Google redirect URI must use https in production")
            if problems:
                raise ValueError("; ".join(problems))
            if _is_loopback_only(self.forwarded_allow_ips):
                log.warning(
                    "FORWARDED_ALLOW_IPS trusts only loopback: behind a reverse proxy every client shares "
                    "the proxy's address, so per-IP rate limits apply to all users together"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
