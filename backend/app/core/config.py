"""Environment-driven settings.

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase (PRD §6/§9.2). SecretStr so an accidental repr()/print() of
    # `settings` (a debugger, a stray log line, a future bug) shows
    # `SecretStr('**********')` instead of the real value — call
    # `.get_secret_value()` explicitly at the one call site that needs it.
    #
    # No JWT secret here: this project signs with asymmetric JWT Signing
    # Keys (ES256), not a shared HS256 secret, so auth/dependencies.py
    # verifies against Supabase's public JWKS (derived from supabase_url)
    # instead of a configured secret.
    supabase_url: str = ""
    supabase_service_role_key: SecretStr = SecretStr("")

    # Database — Postgres is the source of truth for job state (PRD §2).
    # SecretStr: the DSN embeds a password.
    database_url: SecretStr = SecretStr("postgresql+psycopg://depthwizard:depthwizard@localhost:5432/depthwizard")

    # Redis — Celery broker only, never job status (PRD §2).
    # SecretStr: the DSN can embed a password (e.g. Upstash in prod).
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")

    # Storage — one private bucket, prefixed by inputs/staging/outputs/compares (PRD §7)
    storage_bucket: str = "depthwizard"

    # Upload limit (PRD §9.5)
    max_upload_mb: int = 50

    # Signed URL expiry (PRD §7 — 60 minutes)
    signed_url_expiry_minutes: int = 60

    # CORS
    cors_allow_origins: str = "http://localhost:5173"

    # Hard per-task timeout (PRD §9.7 — every task carries one)
    celery_task_time_limit_seconds: int = 600

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def cors_origins_list(self) -> list[str]:
        """Explicit origins only — never "*". main.py sets
        allow_credentials=True, and browsers reject a wildcard origin
        combined with credentials outright; there's no server-side way
        around that. Also strips trailing slashes and requires a scheme:
        the browser's Origin header is always exactly `scheme://host[:port]`
        — no path, no trailing slash — so a mismatch here fails silently as
        a browser-console CORS error, not a Python exception. Better to
        fail loud here, at startup, than have someone debug a "silent" CORS
        rejection later.
        """
        origins = [origin.strip().rstrip("/") for origin in self.cors_allow_origins.split(",") if origin.strip()]
        for origin in origins:
            if origin == "*":
                raise ValueError(
                    "CORS_ALLOW_ORIGINS must not be '*' — this API sets allow_credentials=True, "
                    "and browsers reject a wildcard origin combined with credentials. List explicit origins."
                )
            if not origin.startswith(("http://", "https://")):
                raise ValueError(
                    f"CORS_ALLOW_ORIGINS entry {origin!r} is missing a scheme (http:// or https://) — "
                    "the browser's Origin header always includes one, so this would never match."
                )
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
