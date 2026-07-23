from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class ProductionConfig:
    environment: str
    database_url: str | None
    session_secret: str
    allowed_origins: tuple[str, ...]
    cookie_secure: bool
    db_pool_size: int
    db_max_overflow: int
    db_pool_recycle: int
    browser_profile_root: Path
    runtime_host: str
    browser_idle_timeout_minutes: int
    max_queued_executions_per_tenant: int
    worker_concurrency: int
    execution_retention_days: int
    artifact_retention_days: int
    heartbeat_stale_seconds: int
    queue_stale_seconds: int
    login_rate_limit_per_minute: int
    log_level: str
    app_version: str
    git_commit: str
    build_time: str
    enable_demo_seed: bool
    bootstrap_admin_email: str | None
    bootstrap_admin_password: str | None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ProductionConfig":
        env = environ or os.environ
        environment = env.get("SAAS_ENV", "development").strip().lower()
        is_production = environment == "production"
        session_secret = env.get("SESSION_SECRET", "").strip()
        origins_value = env.get("SAAS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        allowed_origins = tuple(origin.strip() for origin in origins_value.split(",") if origin.strip())
        database_url = env.get("DATABASE_URL", "").strip() or None

        if is_production and len(session_secret) < 32:
            raise RuntimeError("SESSION_SECRET must be set to at least 32 characters in production")
        if "*" in allowed_origins:
            raise RuntimeError("SAAS_ALLOWED_ORIGINS cannot contain a wildcard when credentials are enabled")
        if is_production and not allowed_origins:
            raise RuntimeError("SAAS_ALLOWED_ORIGINS is required in production")
        if is_production and not database_url:
            raise RuntimeError("DATABASE_URL is required in production")

        runtime_host = env.get("SAAS_RUNTIME_HOST", "local").strip().lower()
        if runtime_host not in {"local", "windows-agent"}:
            raise RuntimeError("SAAS_RUNTIME_HOST must be local or windows-agent")

        return cls(
            environment=environment,
            database_url=database_url,
            session_secret=session_secret or "development-only-session-secret",
            allowed_origins=allowed_origins,
            cookie_secure=_bool(env.get("SAAS_COOKIE_SECURE"), default=is_production),
            db_pool_size=_int(env, "SAAS_DB_POOL_SIZE", 10, minimum=1),
            db_max_overflow=_int(env, "SAAS_DB_MAX_OVERFLOW", 20, minimum=0),
            db_pool_recycle=_int(env, "SAAS_DB_POOL_RECYCLE", 1800, minimum=1),
            browser_profile_root=Path(env.get("SAAS_BROWSER_PROFILE_ROOT", "data/browser_profiles")),
            runtime_host=runtime_host,
            browser_idle_timeout_minutes=_int(env, "SAAS_BROWSER_IDLE_TIMEOUT_MINUTES", 30, minimum=1),
            max_queued_executions_per_tenant=_int(env, "SAAS_MAX_QUEUED_EXECUTIONS_PER_TENANT", 50, minimum=1),
            worker_concurrency=_int(env, "SAAS_WORKER_CONCURRENCY", 1, minimum=1),
            execution_retention_days=_int(env, "SAAS_EXECUTION_RETENTION_DAYS", 90, minimum=1),
            artifact_retention_days=_int(env, "SAAS_ARTIFACT_RETENTION_DAYS", 30, minimum=1),
            heartbeat_stale_seconds=_int(env, "SAAS_HEARTBEAT_STALE_SECONDS", 60, minimum=1),
            queue_stale_seconds=_int(env, "SAAS_QUEUE_STALE_SECONDS", 21600, minimum=60),
            login_rate_limit_per_minute=_int(env, "SAAS_LOGIN_RATE_LIMIT_PER_MINUTE", 5, minimum=1),
            log_level=env.get("LOG_LEVEL", "INFO").strip().upper(),
            app_version=env.get("APP_VERSION", "7.4.0").strip(),
            git_commit=env.get("GIT_COMMIT", "unknown").strip(),
            build_time=env.get("BUILD_TIME", "unknown").strip(),
            enable_demo_seed=_bool(env.get("SAAS_ENABLE_DEMO_SEED"), default=False),
            bootstrap_admin_email=env.get("SAAS_BOOTSTRAP_ADMIN_EMAIL", "").strip() or None,
            bootstrap_admin_password=env.get("SAAS_BOOTSTRAP_ADMIN_PASSWORD", "").strip() or None,
        )


def _bool(value: str | None, *, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise RuntimeError("boolean environment values must be true or false")
    return normalized == "true"


def _int(env: Mapping[str, str], name: str, default: int, *, minimum: int) -> int:
    try:
        value = int(env.get(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value
