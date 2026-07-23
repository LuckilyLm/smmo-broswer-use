from __future__ import annotations

import os
import hashlib
import hmac
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .db import utc_now
from .config import ProductionConfig
from .logging import configure_logging
from .models import TenantContext
from .runtime import BrowserRuntimeError
from .service import SaaSService
from .storage import SaaSStorage

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

SESSION_COOKIE = "leadflow_session"


class LoginRateLimiter:
    def __init__(self, limit: int, *, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.failures: dict[str, deque[float]] = defaultdict(deque)

    def allowed(self, key: str) -> bool:
        failures = self.failures[key]
        cutoff = time.monotonic() - self.window_seconds
        while failures and failures[0] < cutoff:
            failures.popleft()
        return len(failures) < self.limit

    def record_failure(self, key: str) -> None:
        self.failures[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self.failures.pop(key, None)


def create_app(*, database_url: str | None = None, service: SaaSService | None = None, config: ProductionConfig | None = None) -> FastAPI:
    config = config or ProductionConfig.from_env()
    service_instance = service or SaaSService(SaaSStorage(database_url, create_schema=False))
    logger = configure_logging("api", config.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        reconciled = service_instance.runtime_registry.reconcile_all()
        bootstrapped = service_instance.bootstrap_admin(config.bootstrap_admin_email, config.bootstrap_admin_password)
        logger.info("startup reconciliation complete", extra={"reconciled_runtimes": reconciled, "admin_bootstrapped": bool(bootstrapped)})
        yield

    app = FastAPI(title="Facebook Leads SaaS API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.config = config
    app.state.service = service_instance
    app.state.login_rate_limiter = LoginRateLimiter(config.login_rate_limit_per_minute)

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        code = {400: "bad_request", 401: "session_expired", 403: "permission_denied", 404: "not_found", 409: "conflict", 429: "rate_limit_reached", 503: "service_unavailable"}.get(exc.status_code, "request_failed")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        if message == "queue_limit_reached":
            code = "queue_limit_reached"
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": code, "message": message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Request validation failed"}})

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Internal server error"}})

    def get_service() -> SaaSService:
        return app.state.service

    def require_context(
        authorization: str = Header(default=""),
        session_cookie: str = Cookie(default="", alias=SESSION_COOKIE),
        svc: SaaSService = Depends(get_service),
    ) -> TenantContext:
        token = _session_token(authorization, session_cookie, config.session_secret)
        try:
            return svc.context_from_token(token)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/version")
    def version() -> dict[str, str]:
        return {"app_version": config.app_version, "git_commit": config.git_commit, "build_time": config.build_time}

    @app.get("/api/ready")
    def ready(svc: SaaSService = Depends(get_service)) -> dict[str, str]:
        try:
            svc.storage.ping()
            if not svc.storage.schema_current():
                raise RuntimeError("schema is not current")
            return {"status": "ready", "database": "ok", "schema": "ok"}
        except Exception as exc:
            raise HTTPException(status_code=503, detail={"status": "not_ready", "database": "error", "reason": type(exc).__name__}) from exc

    @app.post("/api/auth/login")
    def login(payload: dict[str, Any], response: Response, request: Request, svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        client_key = request.client.host if request.client else "unknown"
        if not app.state.login_rate_limiter.allowed(client_key):
            raise HTTPException(status_code=429, detail="Too many login attempts")
        try:
            result = svc.login(payload.get("email", ""), payload.get("password", ""))
            app.state.login_rate_limiter.reset(client_key)
            response.set_cookie(
                SESSION_COOKIE,
                _sign_session_token(result["access_token"], config.session_secret),
                httponly=True,
                secure=config.cookie_secure,
                samesite="lax",
                path="/",
            )
            return result
        except PermissionError as exc:
            app.state.login_rate_limiter.record_failure(client_key)
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.post("/api/auth/logout")
    def logout(
        response: Response,
        authorization: str = Header(default=""),
        session_cookie: str = Cookie(default="", alias=SESSION_COOKIE),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, bool]:
        svc.logout(_session_token(authorization, session_cookie, config.session_secret))
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.me(context)

    @app.get("/api/tenants")
    def tenants(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        return svc.tenants(context)

    @app.post("/api/tenants/{tenant_id}/switch")
    def switch_tenant(
        tenant_id: str,
        authorization: str = Header(default=""),
        session_cookie: str = Cookie(default="", alias=SESSION_COOKIE),
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        switched = svc.switch_tenant(context, tenant_id)
        token = _session_token(authorization, session_cookie, config.session_secret)
        svc.storage.update_by_id("sessions", token, {"tenant_id": switched.tenant_id})
        return {"tenant_id": switched.tenant_id}

    @app.get("/api/dashboard/summary")
    def dashboard(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.dashboard_summary(context)

    @app.get("/api/platform-accounts")
    def list_platform_accounts(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        return svc.list_platform_accounts(context)

    @app.post("/api/platform-accounts")
    def create_platform_account(payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.create_platform_account(context, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/platform-accounts/{account_id}")
    def update_platform_account(account_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            row = svc.update_platform_account(context, account_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @app.delete("/api/platform-accounts/{account_id}", status_code=204)
    def delete_platform_account(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        svc.delete_platform_account(context, account_id)
        return Response(status_code=204)

    @app.post("/api/platform-accounts/{account_id}/connect")
    def connect_platform_account(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.connect_platform_account(context, account_id)
        except BrowserRuntimeError as exc:
            raise HTTPException(status_code=400, detail={"error_type": exc.error_type, "message": str(exc)}) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="not found") from exc

    @app.post("/api/platform-accounts/{account_id}/check-login")
    async def check_platform_login(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return await svc.check_platform_login(context, account_id)
        except BrowserRuntimeError as exc:
            raise HTTPException(status_code=400, detail={"error_type": exc.error_type, "message": str(exc)}) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="not found") from exc

    @app.post("/api/platform-accounts/{account_id}/reconnect")
    def reconnect_platform_account(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.reconnect_platform_account(context, account_id)

    @app.post("/api/platform-accounts/{account_id}/stop-runtime")
    def stop_platform_runtime(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.stop_platform_runtime(context, account_id)

    @app.post("/api/platform-accounts/{account_id}/restart-runtime")
    def restart_platform_runtime(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.restart_platform_runtime(context, account_id)

    @app.post("/api/platform-accounts/{account_id}/reset-profile")
    def reset_platform_profile(account_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.reset_platform_profile(context, account_id, confirm=payload.get("confirm", ""))
        except BrowserRuntimeError as exc:
            raise HTTPException(status_code=400, detail={"error_type": exc.error_type, "message": str(exc)}) from exc

    @app.get("/api/platform-accounts/{account_id}/runtime")
    def get_platform_runtime(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            runtime = svc.get_platform_runtime(context, account_id)
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="not found") from exc
        if not runtime:
            raise HTTPException(status_code=404, detail="not found")
        return runtime

    @app.get("/api/campaigns")
    def list_campaigns(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        return svc.list_campaigns(context)

    @app.post("/api/campaigns")
    def create_campaign(payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.create_campaign(context, payload)
        except (PermissionError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/campaigns/{campaign_id}")
    def update_campaign(campaign_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            row = svc.update_campaign(context, campaign_id, payload)
        except (PermissionError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @app.delete("/api/campaigns/{campaign_id}", status_code=204)
    def delete_campaign(campaign_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        svc.delete_campaign(context, campaign_id)
        return Response(status_code=204)

    @app.post("/api/campaigns/{campaign_id}/run")
    async def run_campaign(campaign_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return await svc.run_campaign(context, campaign_id)
        except (PermissionError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/campaigns/{campaign_id}/schedule")
    def get_campaign_schedule(campaign_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.get_campaign_schedule(context, campaign_id) or {"campaign_id": campaign_id, "enabled": False, "schedule_type": "manual", "timezone": "UTC"}
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="not found") from exc

    @app.put("/api/campaigns/{campaign_id}/schedule")
    def put_campaign_schedule(campaign_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.put_campaign_schedule(context, campaign_id, payload)
        except (PermissionError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/campaigns/{campaign_id}/schedule/disable")
    def disable_campaign_schedule(campaign_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.disable_campaign_schedule(context, campaign_id)
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="not found") from exc

    @app.get("/api/campaigns/{campaign_id}/keywords")
    def list_keywords(campaign_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        return svc.list_keywords(context, campaign_id)

    @app.post("/api/campaigns/{campaign_id}/keywords")
    def create_keyword(campaign_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.create_keyword(context, campaign_id, payload)

    @app.patch("/api/keywords/{keyword_id}")
    def update_keyword(keyword_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        row = svc.update_keyword(context, keyword_id, payload)
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @app.delete("/api/keywords/{keyword_id}", status_code=204)
    def delete_keyword(keyword_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        svc.delete_keyword(context, keyword_id)
        return Response(status_code=204)

    @app.get("/api/leads")
    def list_leads(
        campaign_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
        rule_intent_level: str | None = None,
        reply_allowed: bool | None = None,
        keyword: str | None = None,
        limit: int = 50,
        offset: int = 0,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        return svc.list_leads(
            context,
            {
                "campaign_id": campaign_id,
                "platform": platform,
                "status": status,
                "rule_intent_level": rule_intent_level,
                "reply_allowed": reply_allowed,
                "keyword": keyword,
            },
            limit=limit,
            offset=offset,
        )

    @app.get("/api/leads/{lead_id}")
    def get_lead(lead_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        row = svc.get_lead(context, lead_id)
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @app.get("/api/reply-rules")
    def list_reply_rules(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        return svc.list_reply_rules(context)

    @app.post("/api/reply-rules")
    def create_reply_rule(payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.create_reply_rule(context, payload)
        except (PermissionError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/reply-rules/{rule_id}")
    def update_reply_rule(rule_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        row = svc.update_reply_rule(context, rule_id, payload)
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @app.delete("/api/reply-rules/{rule_id}", status_code=204)
    def delete_reply_rule(rule_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        svc.delete_reply_rule(context, rule_id)
        return Response(status_code=204)

    @app.get("/api/executions")
    def list_executions(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        return svc.list_executions(context)

    @app.get("/api/executions/{execution_id}")
    def get_execution(execution_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        row = svc.get_execution(context, execution_id)
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @app.get("/api/executions/{execution_id}/keywords")
    def get_execution_keywords(execution_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        try:
            return svc.list_execution_keywords(context, execution_id)
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="not found") from exc

    @app.post("/api/executions/{execution_id}/cancel")
    def cancel_execution(execution_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.cancel_execution(context, execution_id)
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="not found") from exc

    @app.get("/api/system/worker-status")
    def worker_status(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        del context
        now = utc_now()
        row = svc.storage.query_all(
            "SELECT COUNT(*) AS worker_count, MAX(last_seen_at) AS last_heartbeat_at FROM worker_heartbeats WHERE worker_id <> ? AND status IN (?, ?, ?) AND last_seen_at >= ?",
            ["scheduler", "online", "polling", "running", now - timedelta(seconds=config.heartbeat_stale_seconds)],
        )[0]
        return {"online": int(row["worker_count"]) > 0, "last_heartbeat_at": row["last_heartbeat_at"], "worker_count": int(row["worker_count"])}

    @app.get("/api/system/scheduler-status")
    def scheduler_status(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        queue_counts = svc.storage.queue_counts(tenant_id=context.tenant_id)
        now = utc_now()
        due = svc.storage.query_all(
            "SELECT COUNT(*) AS count FROM campaign_schedules WHERE tenant_id = ? AND enabled = ? AND next_run_at IS NOT NULL AND next_run_at <= ?",
            [context.tenant_id, True, now],
        )[0]["count"]
        scheduler_heartbeat = svc.storage.find_one("worker_heartbeats", {"worker_id": "scheduler"})
        scheduler_online = bool(
            scheduler_heartbeat
            and scheduler_heartbeat.get("status") == "online"
            and _as_utc_datetime(scheduler_heartbeat["last_seen_at"]) >= now - timedelta(seconds=config.heartbeat_stale_seconds)
        )
        return {
            "online": scheduler_online,
            "last_tick_at": scheduler_heartbeat.get("last_seen_at") if scheduler_heartbeat else None,
            "due_campaign_count": int(due),
            "last_error": scheduler_heartbeat.get("last_error") if scheduler_heartbeat else None,
            "queued_tasks": queue_counts.get("queued", 0) + queue_counts.get("retry_waiting", 0),
            "running_tasks": queue_counts.get("running", 0),
        }

    @app.get("/api/token-usage/summary")
    def token_summary(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.token_usage_summary(context)

    @app.get("/api/token-usage/details")
    def token_details(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.token_usage_details(context)

    @app.get("/api/settings")
    def settings(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        tenant = svc.storage.get_by_id("tenants", context.tenant_id)
        return {"tenant": tenant, "send_disabled": True, "approval_mode": "manual"}

    return app


_default_database_url = os.getenv("DATABASE_URL")
if _default_database_url:
    app = create_app(database_url=_default_database_url)
else:
    app = create_app(database_url="sqlite:///artifacts/saas/saas.sqlite")


def _sign_session_token(token: str, secret: str) -> str:
    signature = hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{token}.{signature}"


def _session_token(authorization: str, session_cookie: str, secret: str) -> str:
    bearer = authorization.removeprefix("Bearer ").strip()
    if bearer:
        return bearer
    token, separator, signature = session_cookie.strip().partition(".")
    if not separator or not token or not signature:
        return ""
    expected = hmac.new(secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()
    return token if hmac.compare_digest(signature, expected) else ""


def _as_utc_datetime(value: Any) -> datetime:
    if hasattr(value, "tzinfo"):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
