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

    # Traversal limits
    max_traversal_depth: int = 25

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
            if not self.cookie_secure:
                problems.append("VSH_COOKIE_SECURE must be true in production")
            if problems:
                raise ValueError("; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
