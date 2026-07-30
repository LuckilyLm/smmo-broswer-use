from __future__ import annotations

import os
import platform
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
    deployment_mode: str
    runtime_host: str
    browser_cdp_base_url: str
    browser_cdp_bind_address: str
    browser_runtime_control_url: str | None
    browser_cdp_port_start: int
    browser_cdp_port_end: int
    browser_headless: bool
    browser_idle_timeout_minutes: int
    max_queued_executions_per_tenant: int
    worker_concurrency: int
    execution_retention_days: int
    artifact_retention_days: int
    heartbeat_stale_seconds: int
    queue_stale_seconds: int
    worker_heartbeat_interval_seconds: int
    scheduler_queue_full_retry_minutes: int
    session_ttl_hours: int
    session_idle_timeout_hours: int
    login_rate_limit_per_minute: int
    log_level: str
    app_version: str
    git_commit: str
    build_time: str
    enable_demo_seed: bool
    bootstrap_admin_email: str | None
    bootstrap_admin_password: str | None
    bootstrap_system_admin_email: str | None
    trust_proxy: bool
    llm_input_cost_per_1m: float | None
    llm_output_cost_per_1m: float | None
    llm_endpoint: str | None
    llm_api_key: str | None
    llm_model: str
    artifact_s3_enabled: bool
    artifact_s3_endpoint: str | None
    artifact_s3_access_key: str | None
    artifact_s3_secret_key: str | None
    artifact_s3_bucket: str | None
    artifact_s3_region: str
    artifact_s3_prefix: str
    artifact_s3_public_base_url: str | None
    artifact_s3_secure: bool
    system_send_enabled: bool

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def browser_platform(self) -> str:
        return platform.system()

    @property
    def local_browser_supported(self) -> bool:
        return self.runtime_host == "local"

    @property
    def runtime_available(self) -> bool:
        return (
            self.deployment_mode == "browser-use"
            and self.runtime_host in {"local", "remote"}
            and (self.runtime_host == "remote" or self.local_browser_supported)
        )

    def runtime_capabilities(self) -> dict[str, object]:
        return {
            "runtime_host": self.runtime_host,
            "runtime_available": self.runtime_available,
            "browser_platform": self.browser_platform,
            "local_browser_supported": self.local_browser_supported,
            "browser_backend": "browser-use",
            "browser_headless": self.browser_headless,
            "browser_cdp_base_url": self.browser_cdp_base_url,
        }

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

        deployment_mode = env.get("SAAS_DEPLOYMENT_MODE", "browser-use").strip().lower()
        if deployment_mode not in {"browser-use", "control-plane-only"}:
            raise RuntimeError("SAAS_DEPLOYMENT_MODE must be browser-use or control-plane-only")
        runtime_host = env.get("SAAS_RUNTIME_HOST", "local").strip().lower()
        if runtime_host not in {"local", "remote"}:
            raise RuntimeError("SAAS_RUNTIME_HOST must be local or remote")
        browser_cdp_base_url = env.get("SAAS_BROWSER_CDP_BASE_URL", "").strip().rstrip("/")
        if not browser_cdp_base_url:
            browser_cdp_base_url = "http://127.0.0.1" if runtime_host == "local" else "http://saas-browser-runtime"
        browser_runtime_control_url = env.get("SAAS_BROWSER_RUNTIME_CONTROL_URL", "").strip().rstrip("/") or None
        if runtime_host == "remote" and not browser_runtime_control_url:
            browser_runtime_control_url = "http://saas-browser-runtime:8001"
        cdp_port_start = _int(env, "SAAS_BROWSER_CDP_PORT_START", 9300, minimum=1)
        cdp_port_end = _int(env, "SAAS_BROWSER_CDP_PORT_END", 9399, minimum=1)
        if cdp_port_end < cdp_port_start:
            raise RuntimeError("SAAS_BROWSER_CDP_PORT_END must be greater than or equal to SAAS_BROWSER_CDP_PORT_START")

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
            deployment_mode=deployment_mode,
            runtime_host=runtime_host,
            browser_cdp_base_url=browser_cdp_base_url,
            browser_cdp_bind_address=env.get("SAAS_BROWSER_CDP_BIND_ADDRESS", "127.0.0.1").strip() or "127.0.0.1",
            browser_runtime_control_url=browser_runtime_control_url,
            browser_cdp_port_start=cdp_port_start,
            browser_cdp_port_end=cdp_port_end,
            browser_headless=_bool(env.get("SAAS_BROWSER_HEADLESS"), default=platform.system() != "Windows"),
            browser_idle_timeout_minutes=_int(env, "SAAS_BROWSER_IDLE_TIMEOUT_MINUTES", 30, minimum=1),
            max_queued_executions_per_tenant=_int(env, "SAAS_MAX_QUEUED_EXECUTIONS_PER_TENANT", 50, minimum=1),
            worker_concurrency=_int(env, "SAAS_WORKER_CONCURRENCY", 1, minimum=1),
            execution_retention_days=_int(env, "SAAS_EXECUTION_RETENTION_DAYS", 90, minimum=1),
            artifact_retention_days=_int(env, "SAAS_ARTIFACT_RETENTION_DAYS", 30, minimum=1),
            heartbeat_stale_seconds=_int(env, "SAAS_HEARTBEAT_STALE_SECONDS", 60, minimum=1),
            queue_stale_seconds=_int(env, "SAAS_QUEUE_STALE_SECONDS", 21600, minimum=60),
            worker_heartbeat_interval_seconds=_int(env, "SAAS_WORKER_HEARTBEAT_INTERVAL_SECONDS", 15, minimum=1),
            scheduler_queue_full_retry_minutes=_int(env, "SAAS_SCHEDULER_QUEUE_FULL_RETRY_MINUTES", 5, minimum=1),
            session_ttl_hours=_int(env, "SAAS_SESSION_TTL_HOURS", 168, minimum=1),
            session_idle_timeout_hours=_int(env, "SAAS_SESSION_IDLE_TIMEOUT_HOURS", 24, minimum=1),
            login_rate_limit_per_minute=_int(env, "SAAS_LOGIN_RATE_LIMIT_PER_MINUTE", 5, minimum=1),
            log_level=env.get("LOG_LEVEL", "INFO").strip().upper(),
            app_version=env.get("APP_VERSION", "7.6.0").strip(),
            git_commit=env.get("GIT_COMMIT", "unknown").strip(),
            build_time=env.get("BUILD_TIME", "unknown").strip(),
            enable_demo_seed=_bool(env.get("SAAS_ENABLE_DEMO_SEED"), default=False),
            bootstrap_admin_email=env.get("SAAS_BOOTSTRAP_ADMIN_EMAIL", "").strip() or None,
            bootstrap_admin_password=env.get("SAAS_BOOTSTRAP_ADMIN_PASSWORD", "").strip() or None,
            bootstrap_system_admin_email=env.get("SAAS_BOOTSTRAP_SYSTEM_ADMIN_EMAIL", "").strip() or None,
            trust_proxy=_bool(env.get("SAAS_TRUST_PROXY"), default=False),
            llm_input_cost_per_1m=_optional_float(env, "SAAS_LLM_INPUT_COST_PER_1M"),
            llm_output_cost_per_1m=_optional_float(env, "SAAS_LLM_OUTPUT_COST_PER_1M"),
            llm_endpoint=env.get("SAAS_LLM_ENDPOINT", "").strip() or env.get("OPENAI_ENDPOINT", "").strip() or env.get("OPENAI_BASE_URL", "").strip() or None,
            llm_api_key=env.get("OPENAI_API_KEY", "").strip() or None,
            llm_model=env.get("SAAS_LLM_MODEL", "").strip() or env.get("FACEBOOK_LEADS_LLM_MODEL", "gpt-5.5").strip() or "gpt-5.5",
            artifact_s3_enabled=_bool(env.get("SAAS_ARTIFACT_S3_ENABLED"), default=False),
            artifact_s3_endpoint=env.get("SAAS_ARTIFACT_S3_ENDPOINT", "").strip() or None,
            artifact_s3_access_key=env.get("SAAS_ARTIFACT_S3_ACCESS_KEY", "").strip() or None,
            artifact_s3_secret_key=env.get("SAAS_ARTIFACT_S3_SECRET_KEY", "").strip() or None,
            artifact_s3_bucket=env.get("SAAS_ARTIFACT_S3_BUCKET", "").strip() or None,
            artifact_s3_region=env.get("SAAS_ARTIFACT_S3_REGION", "us-east-1").strip() or "us-east-1",
            artifact_s3_prefix=env.get("SAAS_ARTIFACT_S3_PREFIX", "saas-artifacts").strip().strip("/"),
            artifact_s3_public_base_url=env.get("SAAS_ARTIFACT_S3_PUBLIC_BASE_URL", "").strip().rstrip("/") or None,
            artifact_s3_secure=_bool(env.get("SAAS_ARTIFACT_S3_SECURE"), default=True),
            system_send_enabled=_bool(env.get("SAAS_SYSTEM_SEND_ENABLED"), default=False),
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


def _optional_float(env: Mapping[str, str], name: str) -> float | None:
    raw = env.get(name, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if value < 0:
        raise RuntimeError(f"{name} must be at least 0")
    return value
