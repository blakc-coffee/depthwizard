"""Environment-driven settings.

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase (PRD §6/§9.2)
    supabase_url: str = ""
    supabase_jwt_secret: str = ""
    supabase_service_role_key: str = ""

    # Database — Postgres is the source of truth for job state (PRD §2)
    database_url: str = "postgresql+psycopg://depthwizard:depthwizard@localhost:5432/depthwizard"

    # Redis — Celery broker only, never job status (PRD §2)
    redis_url: str = "redis://localhost:6379/0"

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
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
