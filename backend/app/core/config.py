"""Application settings (12-factor: everything from environment variables)."""

from __future__ import annotations

import base64
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Development-only keys. Production refuses to start with these (see validate_production).
_DEV_STANDARD_KEY = base64.b64encode(b"vanshavali-dev-standard-key-32b!").decode()
_DEV_VAULT_KEY = base64.b64encode(b"vanshavali-dev-vault-key-32bytes").decode()
_DEV_SIGNING_KEY = "vanshavali-dev-signing-key-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VSH_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    app_name: str = "Vanshavali"
    api_prefix: str = "/api/v1"
    public_base_url: str = "http://localhost:3000"

    database_url: str = "postgresql+psycopg://vanshavali:vanshavali@localhost:5432/vanshavali"
    redis_url: str = "redis://localhost:6379/0"
    # Per-statement timeout for API/worker connections (0 disables); protects against runaway queries.
    statement_timeout_ms: int = 15000

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
            if self.signing_key == _DEV_SIGNING_KEY:
                problems.append("VSH_SIGNING_KEY must be set in production")
            if self.mail_backend != "smtp":
                problems.append("VSH_MAIL_BACKEND must be 'smtp' in production")
            elif not self.smtp_host or not self.smtp_starttls:
                problems.append("VSH_SMTP_HOST must be set and STARTTLS enabled in production")
            if not self.cookie_secure:
                problems.append("VSH_COOKIE_SECURE must be true in production")
            if self.google_enabled and not self.google_callback_uri.startswith("https://"):
                problems.append("the Google redirect URI must use https in production")
            if problems:
                raise ValueError("; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
