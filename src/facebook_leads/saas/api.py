from __future__ import annotations

import os
import hashlib
import hmac
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn

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
from .runtime import BrowserRuntimeRegistry
from .routers.system import build_system_router
from .routers.auth import create_router as create_auth_router
from .routers.campaigns import create_router as create_campaigns_router
from .routers.executions import create_router as create_executions_router
from .routers.leads import create_router as create_leads_router
from .routers.platform_accounts import create_router as create_platform_accounts_router
from .schemas import (
    AcceptInvitationRequest,
    ChangePasswordRequest,
    CreatePlanRequest,
    CreateCampaignRequest,
    CreatePlatformAccountRequest,
    InviteMemberRequest,
    LoginRequest,
    ResetProfileRequest,
    ScheduleRequest,
    TransferOwnershipRequest,
    UpdateMemberRoleRequest,
    UpdatePlanRequest,
    UpdateSubscriptionRequest,
    UpdateTenantSettingsRequest,
    UpdateCampaignRequest,
)
from .productization import (
    FeatureNotAvailableError,
    QuotaExceededError,
    backfill_legacy_subscriptions,
    seed_plans,
)
from .service import SaaSService, ServiceConflictError
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
    if service is None:
        storage = SaaSStorage(database_url or config.database_url, create_schema=False)
        runtime_registry = BrowserRuntimeRegistry(
            storage,
            profiles_root=config.browser_profile_root,
            chrome_executable=config.chrome_executable,
            cdp_port_start=config.browser_cdp_port_start,
            cdp_port_end=config.browser_cdp_port_end,
            runtime_host=config.runtime_host,
            allow_chrome_discovery=not config.is_production,
        )
        service_instance = SaaSService(
            storage,
            runtime_registry=runtime_registry,
            max_queued_executions_per_tenant=config.max_queued_executions_per_tenant,
            session_ttl_hours=config.session_ttl_hours,
            session_idle_timeout_hours=config.session_idle_timeout_hours,
            config=config,
        )
    else:
        service_instance = service
    logger = configure_logging("api", config.log_level)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        seed_plans(service_instance.storage)
        backfill_legacy_subscriptions(service_instance.storage)
        reconciled = service_instance.runtime_registry.reconcile_all() if config.runtime_available else 0
        bootstrapped = service_instance.bootstrap_admin(config.bootstrap_admin_email, config.bootstrap_admin_password)
        system_admin_bootstrapped = service_instance.bootstrap_system_admin(config.bootstrap_system_admin_email)
        logger.info(
            "startup reconciliation complete",
            extra={
                "reconciled_runtimes": reconciled,
                "bootstrap_admin_created": bool(bootstrapped),
                "bootstrap_system_admin_updated": system_admin_bootstrapped,
                "runtime_available": config.runtime_available,
            },
        )
        yield

    app = FastAPI(title="Facebook Leads SaaS API", lifespan=lifespan)
    auth_router = create_auth_router()
    platform_accounts_router = create_platform_accounts_router()
    campaigns_router = create_campaigns_router()
    leads_router = create_leads_router()
    executions_router = create_executions_router()
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

    @app.middleware("http")
    async def audit_mutations(request: Request, call_next):
        response = await call_next(request)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/") and response.status_code < 400:
            authorization = request.headers.get("authorization", "")
            cookie = request.cookies.get(SESSION_COOKIE, "")
            token = _session_token(authorization, cookie, config.session_secret)
            try:
                context = service_instance.context_from_token(token) if token else None
            except PermissionError:
                context = None
            forwarded = request.headers.get("x-forwarded-for", "") if config.trust_proxy else ""
            ip_address = forwarded.split(",", 1)[0].strip() if forwarded else request.client.host if request.client else None
            service_instance.audit.record(
                action=f"api.{request.method.lower()}",
                resource_type="api",
                resource_id=None,
                tenant_id=context.tenant_id if context else None,
                user_id=context.user_id if context else None,
                ip_address=ip_address,
                user_agent=request.headers.get("user-agent"),
                metadata={"path": request.url.path, "status_code": response.status_code},
            )
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        code = {400: "bad_request", 401: "session_expired", 403: "permission_denied", 404: "not_found", 409: "conflict", 429: "rate_limit_reached", 501: "not_implemented", 503: "service_unavailable"}.get(exc.status_code, "request_failed")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("error_type") or exc.detail.get("code") or code)
            message = str(exc.detail.get("message") or message)
        if message == "queue_limit_reached":
            code = "queue_limit_reached"
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": code, "message": message}})

    @app.exception_handler(BrowserRuntimeError)
    async def browser_runtime_error(_request: Request, exc: BrowserRuntimeError) -> JSONResponse:
        status_code = 501 if exc.error_type in {
            "runtime_host_not_implemented",
            "local_browser_runtime_not_supported",
            "browser_runtime_host_unavailable",
        } else 400
        return JSONResponse(status_code=status_code, content={"error": {"code": exc.error_type, "message": str(exc)}})

    @app.exception_handler(PermissionError)
    async def permission_error(_request: Request, exc: PermissionError) -> JSONResponse:
        not_found = "not found" in str(exc).lower()
        suspended = str(exc) == "tenant_suspended"
        return JSONResponse(
            status_code=404 if not_found else 403,
            content={"error": {"code": "not_found" if not_found else "tenant_suspended" if suspended else "permission_denied", "message": "not found" if not_found else str(exc)}},
        )

    @app.exception_handler(ValueError)
    async def value_error(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": {"code": str(exc), "message": str(exc)}})

    @app.exception_handler(ServiceConflictError)
    async def service_conflict(_request: Request, exc: ServiceConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": str(exc), "message": str(exc)}},
        )

    @app.exception_handler(QuotaExceededError)
    async def quota_exceeded(_request: Request, exc: QuotaExceededError) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "quota_exceeded",
                    "message": str(exc),
                    "resource": exc.resource,
                    "limit": exc.limit,
                    "used": exc.used,
                }
            },
        )

    @app.exception_handler(FeatureNotAvailableError)
    async def feature_not_available(_request: Request, exc: FeatureNotAvailableError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "feature_not_available", "message": str(exc), "feature": exc.feature}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "message": "Request validation failed"}})

    @app.exception_handler(Exception)
    async def internal_error(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "message": "Internal server error"}})

    def get_service() -> SaaSService:
        return app.state.service

    def raise_resource_permission_error(exc: PermissionError) -> NoReturn:
        if str(exc) == "permission denied":
            raise HTTPException(status_code=403, detail="permission denied") from exc
        raise HTTPException(status_code=404, detail="not found") from exc

    def require_context(
        request: Request,
        authorization: str = Header(default=""),
        session_cookie: str = Cookie(default="", alias=SESSION_COOKIE),
        svc: SaaSService = Depends(get_service),
    ) -> TenantContext:
        token = _session_token(authorization, session_cookie, config.session_secret)
        try:
            context = svc.context_from_token(token)
            user = svc.storage.get_by_id("users", context.user_id) or {}
            allowed_during_password_change = {"/api/auth/me", "/api/auth/change-password", "/api/auth/logout"}
            if user.get("must_change_password") and request.url.path not in allowed_during_password_change:
                raise HTTPException(
                    status_code=403,
                    detail={"code": "password_change_required", "message": "Password change required"},
                )
            return context
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

    @auth_router.post("/api/auth/login")
    def login(
        payload: LoginRequest,
        response: Response,
        request: Request,
        session_cookie: str = Cookie(default="", alias=SESSION_COOKIE),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        client_key = request.client.host if request.client else "unknown"
        if not app.state.login_rate_limiter.allowed(client_key):
            raise HTTPException(status_code=429, detail="Too many login attempts")
        try:
            previous_token = _session_token("", session_cookie, config.session_secret)
            if previous_token:
                svc.logout(previous_token)
            result = svc.login(payload.email, payload.password)
            app.state.login_rate_limiter.reset(client_key)
            response.set_cookie(
                SESSION_COOKIE,
                _sign_session_token(result["access_token"], config.session_secret),
                httponly=True,
                secure=config.cookie_secure,
                samesite="lax",
                path="/",
                max_age=config.session_ttl_hours * 3600,
            )
            return result
        except PermissionError as exc:
            app.state.login_rate_limiter.record_failure(client_key)
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @auth_router.post("/api/auth/logout")
    def logout(
        response: Response,
        authorization: str = Header(default=""),
        session_cookie: str = Cookie(default="", alias=SESSION_COOKIE),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, bool]:
        svc.logout(_session_token(authorization, session_cookie, config.session_secret))
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"ok": True}

    @auth_router.get("/api/auth/me")
    def me(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.me(context)

    @auth_router.post("/api/auth/change-password")
    def change_password(
        payload: ChangePasswordRequest,
        response: Response,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, bool]:
        try:
            svc.change_password(context, payload.current_password, payload.new_password)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"ok": True}

    @auth_router.get("/api/tenants")
    def tenants(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        return svc.tenants(context)

    @auth_router.post("/api/tenants/{tenant_id}/switch")
    def switch_tenant(
        tenant_id: str,
        response: Response,
        authorization: str = Header(default=""),
        session_cookie: str = Cookie(default="", alias=SESSION_COOKIE),
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        token = _session_token(authorization, session_cookie, config.session_secret)
        rotated = svc.rotate_session(token, tenant_id)
        response.set_cookie(
            SESSION_COOKIE,
            _sign_session_token(rotated["access_token"], config.session_secret),
            httponly=True,
            secure=config.cookie_secure,
            samesite="lax",
            max_age=config.session_ttl_hours * 3600,
            path="/",
        )
        return {"tenant_id": rotated["tenant_id"], "access_token": rotated["access_token"]}

    @app.get("/api/dashboard/summary")
    def dashboard(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.dashboard_summary(context)

    @platform_accounts_router.get("/api/platform-accounts")
    def list_platform_accounts(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        return svc.list_platform_accounts(context)

    @platform_accounts_router.post("/api/platform-accounts")
    def create_platform_account(payload: CreatePlatformAccountRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.create_platform_account(context, payload.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @platform_accounts_router.patch("/api/platform-accounts/{account_id}")
    def update_platform_account(account_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            row = svc.update_platform_account(context, account_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @platform_accounts_router.delete("/api/platform-accounts/{account_id}", status_code=204)
    def delete_platform_account(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        svc.delete_platform_account(context, account_id)
        return Response(status_code=204)

    @platform_accounts_router.post("/api/platform-accounts/{account_id}/connect")
    def connect_platform_account(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.connect_platform_account(context, account_id)
        except BrowserRuntimeError as exc:
            status_code = 501 if exc.error_type in {"runtime_host_not_implemented", "local_browser_runtime_not_supported"} else 400
            raise HTTPException(status_code=status_code, detail={"error_type": exc.error_type, "message": str(exc)}) from exc
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @platform_accounts_router.post("/api/platform-accounts/{account_id}/check-login")
    async def check_platform_login(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return await svc.check_platform_login(context, account_id)
        except BrowserRuntimeError as exc:
            status_code = 501 if exc.error_type in {"runtime_host_not_implemented", "local_browser_runtime_not_supported"} else 400
            raise HTTPException(status_code=status_code, detail={"error_type": exc.error_type, "message": str(exc)}) from exc
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @platform_accounts_router.post("/api/platform-accounts/{account_id}/reconnect")
    def reconnect_platform_account(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.reconnect_platform_account(context, account_id)

    @platform_accounts_router.post("/api/platform-accounts/{account_id}/stop-runtime")
    def stop_platform_runtime(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.stop_platform_runtime(context, account_id)

    @platform_accounts_router.post("/api/platform-accounts/{account_id}/restart-runtime")
    def restart_platform_runtime(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.restart_platform_runtime(context, account_id)

    @platform_accounts_router.post("/api/platform-accounts/{account_id}/reset-profile")
    def reset_platform_profile(account_id: str, payload: ResetProfileRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.reset_platform_profile(context, account_id, confirm=payload.confirm)
        except BrowserRuntimeError as exc:
            status_code = 501 if exc.error_type in {"runtime_host_not_implemented", "local_browser_runtime_not_supported"} else 400
            raise HTTPException(status_code=status_code, detail={"error_type": exc.error_type, "message": str(exc)}) from exc

    @platform_accounts_router.get("/api/platform-accounts/{account_id}/runtime")
    def get_platform_runtime(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            runtime = svc.get_platform_runtime(context, account_id)
        except PermissionError as exc:
            raise_resource_permission_error(exc)
        if not runtime:
            raise HTTPException(status_code=404, detail="not found")
        return runtime

    @campaigns_router.get("/api/campaigns")
    def list_campaigns(request: Request, limit: int = 50, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Any:
        safe_limit = min(max(limit, 1), 200)
        items = svc.list_campaigns(context, limit=safe_limit, offset=max(offset, 0))
        if "limit" not in request.query_params and "offset" not in request.query_params:
            return items
        return {
            "items": items,
            "limit": safe_limit,
            "offset": max(offset, 0),
            "total": svc.storage.count("campaigns", tenant_id=context.tenant_id, filters={"deleted_at": None}),
        }

    @campaigns_router.post("/api/campaigns")
    def create_campaign(payload: CreateCampaignRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.create_campaign(context, payload.model_dump(exclude_none=True))
        except PermissionError as exc:
            raise_resource_permission_error(exc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @campaigns_router.patch("/api/campaigns/{campaign_id}")
    def update_campaign(campaign_id: str, payload: UpdateCampaignRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            row = svc.update_campaign(context, campaign_id, payload.model_dump(exclude_none=True))
        except PermissionError as exc:
            raise_resource_permission_error(exc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @campaigns_router.delete("/api/campaigns/{campaign_id}", status_code=204)
    def delete_campaign(campaign_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        svc.delete_campaign(context, campaign_id)
        return Response(status_code=204)

    @campaigns_router.post("/api/campaigns/{campaign_id}/run")
    async def run_campaign(campaign_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return await svc.run_campaign(context, campaign_id)
        except PermissionError as exc:
            raise_resource_permission_error(exc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @campaigns_router.get("/api/campaigns/{campaign_id}/schedule")
    def get_campaign_schedule(campaign_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.get_campaign_schedule(context, campaign_id) or {"campaign_id": campaign_id, "enabled": False, "schedule_type": "manual", "timezone": "UTC"}
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @campaigns_router.put("/api/campaigns/{campaign_id}/schedule")
    def put_campaign_schedule(campaign_id: str, payload: ScheduleRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.put_campaign_schedule(context, campaign_id, payload.model_dump(exclude_none=True))
        except PermissionError as exc:
            raise_resource_permission_error(exc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @campaigns_router.post("/api/campaigns/{campaign_id}/schedule/disable")
    def disable_campaign_schedule(campaign_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.disable_campaign_schedule(context, campaign_id)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @campaigns_router.get("/api/campaigns/{campaign_id}/keywords")
    def list_keywords(campaign_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        return svc.list_keywords(context, campaign_id)

    @campaigns_router.post("/api/campaigns/{campaign_id}/keywords")
    def create_keyword(campaign_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.create_keyword(context, campaign_id, payload)

    @campaigns_router.patch("/api/keywords/{keyword_id}")
    def update_keyword(keyword_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        row = svc.update_keyword(context, keyword_id, payload)
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @campaigns_router.delete("/api/keywords/{keyword_id}", status_code=204)
    def delete_keyword(keyword_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        svc.delete_keyword(context, keyword_id)
        return Response(status_code=204)

    @leads_router.get("/api/leads")
    def list_leads(
        campaign_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
        rule_intent_level: str | None = None,
        final_intent_level: str | None = None,
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
                "final_intent_level": final_intent_level,
                "reply_allowed": reply_allowed,
                "keyword": keyword,
            },
            limit=limit,
            offset=offset,
        )

    @leads_router.get("/api/leads/{lead_id}")
    def get_lead(lead_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        row = svc.get_lead(context, lead_id)
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @campaigns_router.get("/api/reply-rules")
    def list_reply_rules(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        return svc.list_reply_rules(context)

    @campaigns_router.post("/api/reply-rules")
    def create_reply_rule(payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.create_reply_rule(context, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @campaigns_router.patch("/api/reply-rules/{rule_id}")
    def update_reply_rule(rule_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        row = svc.update_reply_rule(context, rule_id, payload)
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @campaigns_router.delete("/api/reply-rules/{rule_id}", status_code=204)
    def delete_reply_rule(rule_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        svc.delete_reply_rule(context, rule_id)
        return Response(status_code=204)

    @campaigns_router.get("/api/reply-templates")
    def list_reply_templates(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        return svc.list_reply_templates(context)

    @campaigns_router.post("/api/reply-templates")
    def create_reply_template(payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.create_reply_template(context, payload)

    @campaigns_router.patch("/api/reply-templates/{template_id}")
    def update_reply_template(template_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        row = svc.update_reply_template(context, template_id, payload)
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @campaigns_router.post("/api/reply-templates/{template_id}/copy")
    def copy_reply_template(template_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.copy_reply_template(context, template_id)

    @campaigns_router.delete("/api/reply-templates/{template_id}", status_code=204)
    def archive_reply_template(template_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        svc.archive_reply_template(context, template_id)
        return Response(status_code=204)

    @campaigns_router.post("/api/reply-templates/preview")
    def preview_reply_template(payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.preview_reply_template(context, payload)

    @campaigns_router.get("/api/reply-match-rules")
    def list_reply_match_rules(campaign_id: str | None = None, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        return svc.list_reply_match_rules(context, campaign_id=campaign_id)

    @campaigns_router.post("/api/reply-match-rules")
    def create_reply_match_rule(payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.create_reply_match_rule(context, payload)

    @campaigns_router.patch("/api/reply-match-rules/{rule_id}")
    def update_reply_match_rule(rule_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        row = svc.update_reply_match_rule(context, rule_id, payload)
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @campaigns_router.delete("/api/reply-match-rules/{rule_id}", status_code=204)
    def delete_reply_match_rule(rule_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        svc.delete_reply_match_rule(context, rule_id)
        return Response(status_code=204)

    @campaigns_router.post("/api/reply-match-rules/test")
    def test_reply_match_rule(payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.test_reply_match_rule(context, payload)

    @campaigns_router.get("/api/reply-candidates")
    def list_reply_candidates(campaign_id: str | None = None, execution_id: str | None = None, reply_plan_id: str | None = None, status: str | None = None, limit: int = 100, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.list_reply_candidates(context, {"campaign_id": campaign_id, "execution_id": execution_id, "reply_plan_id": reply_plan_id, "status": status}, limit=limit, offset=offset)

    @campaigns_router.post("/api/reply-candidates/{candidate_id}/approve")
    def approve_reply_candidate(candidate_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.approve_reply_candidate(context, candidate_id)

    @campaigns_router.post("/api/reply-candidates/{candidate_id}/reject")
    def reject_reply_candidate(candidate_id: str, payload: dict[str, Any] | None = None, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.reject_reply_candidate(context, candidate_id, (payload or {}).get("reason"))

    @campaigns_router.patch("/api/reply-candidates/{candidate_id}/content")
    def update_reply_candidate_content(candidate_id: str, payload: dict[str, Any], context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.update_reply_candidate_content(context, candidate_id, str(payload.get("rendered_reply_text") or ""))

    @campaigns_router.get("/api/reply-plans")
    def list_reply_plans(campaign_id: str | None = None, execution_id: str | None = None, status: str | None = None, limit: int = 100, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.list_reply_plans(context, {"campaign_id": campaign_id, "execution_id": execution_id, "status": status}, limit=limit, offset=offset)

    @campaigns_router.post("/api/reply-plans/{plan_id}/approve")
    def approve_reply_plan(plan_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.approve_reply_plan(context, plan_id)

    @campaigns_router.post("/api/reply-plans/{plan_id}/cancel")
    def cancel_reply_plan(plan_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.cancel_reply_plan(context, plan_id)

    @campaigns_router.post("/api/reply-plans/{plan_id}/execute")
    def execute_reply_plan(plan_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.execute_reply_plan(context, plan_id)

    @campaigns_router.get("/api/reply-records")
    def list_reply_records(limit: int = 100, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.list_reply_records(context, limit=limit, offset=offset)

    @executions_router.get("/api/executions")
    def list_executions(request: Request, limit: int = 50, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Any:
        safe_limit = min(max(limit, 1), 200)
        items = svc.list_executions(context, limit=safe_limit, offset=max(offset, 0))
        if "limit" not in request.query_params and "offset" not in request.query_params:
            return items
        return {
            "items": items,
            "limit": safe_limit,
            "offset": max(offset, 0),
            "total": svc.storage.count("executions", tenant_id=context.tenant_id),
        }

    @executions_router.get("/api/executions/{execution_id}")
    def get_execution(execution_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        row = svc.get_execution(context, execution_id)
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @executions_router.get("/api/executions/{execution_id}/keywords")
    def get_execution_keywords(execution_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        try:
            return svc.list_execution_keywords(context, execution_id)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @executions_router.post("/api/executions/{execution_id}/cancel")
    def cancel_execution(execution_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.cancel_execution(context, execution_id)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

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
    def token_details(limit: int = 50, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.token_usage_details(context, limit=limit, offset=offset)

    @app.get("/api/settings")
    def settings(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        tenant = svc.storage.get_by_id("tenants", context.tenant_id)
        return {"tenant": tenant, "system_send_enabled": config.system_send_enabled, "reply_safety_message": "" if config.system_send_enabled else "回复发送当前处于关闭状态", "approval_mode": "manual"}

    @app.patch("/api/settings")
    def update_settings(
        payload: UpdateTenantSettingsRequest,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        return svc.tenant_admin.update_settings(context, payload.model_dump(exclude_none=True))

    @app.get("/api/usage/summary")
    def usage_summary(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.quota.summary(context.tenant_id)

    @app.get("/api/tenant/members")
    def members(
        limit: int = 50,
        offset: int = 0,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        return svc.tenant_admin.list_members(context, limit=min(max(limit, 1), 200), offset=max(offset, 0))

    @app.post("/api/tenant/members")
    def add_member(
        payload: InviteMemberRequest,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        return svc.tenant_admin.add_member(context, email=payload.email, role=payload.role)

    @app.patch("/api/tenant/members/{membership_id}")
    def update_member(
        membership_id: str,
        payload: UpdateMemberRoleRequest,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        return svc.tenant_admin.update_member(context, membership_id, payload.role)

    @app.delete("/api/tenant/members/{membership_id}", status_code=204)
    def remove_member(
        membership_id: str,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> Response:
        svc.tenant_admin.remove_member(context, membership_id)
        return Response(status_code=204)

    @app.post("/api/tenant/transfer-ownership")
    def transfer_ownership(
        payload: TransferOwnershipRequest,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        return svc.tenant_admin.transfer_ownership(context, payload.target_user_id)

    @app.post("/api/tenant/invitations")
    def create_invitation(
        payload: InviteMemberRequest,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        return svc.tenant_admin.create_invitation(context, email=payload.email, role=payload.role)

    @app.get("/api/tenant/invitations")
    def invitations(
        limit: int = 50,
        offset: int = 0,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        return svc.tenant_admin.list_invitations(context, limit=min(max(limit, 1), 200), offset=max(offset, 0))

    @app.delete("/api/tenant/invitations/{invitation_id}", status_code=204)
    def revoke_invitation(
        invitation_id: str,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> Response:
        svc.tenant_admin.revoke_invitation(context, invitation_id)
        return Response(status_code=204)

    @app.post("/api/invitations/{token}/accept")
    def accept_invitation(
        token: str,
        payload: AcceptInvitationRequest,
        authorization: str = Header(default=""),
        session_cookie: str = Cookie(default="", alias=SESSION_COOKIE),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        authenticated_user_id = None
        session_token = _session_token(authorization, session_cookie, config.session_secret)
        if session_token:
            try:
                authenticated_user_id = svc.context_from_token(session_token).user_id
            except PermissionError:
                authenticated_user_id = None
        return svc.tenant_admin.accept_invitation(
            token,
            authenticated_user_id=authenticated_user_id,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
        )

    @app.get("/api/audit-logs")
    def audit_logs(
        action: str | None = None,
        resource_type: str | None = None,
        user_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        if context.role not in {"owner", "admin"}:
            raise PermissionError("owner or admin role required")
        safe_limit, safe_offset = min(max(limit, 1), 200), max(offset, 0)
        clauses: list[str] = ["tenant_id = ?"]
        values: list[Any] = [context.tenant_id]
        for column, value in (("action", action), ("resource_type", resource_type), ("user_id", user_id)):
            if value:
                clauses.append(f"{column} = ?")
                values.append(value)
        if date_from:
            clauses.append("created_at >= ?")
            values.append(date_from)
        if date_to:
            clauses.append("created_at < ?")
            values.append(date_to)
        where = " AND ".join(clauses)
        total_row = svc.storage.query_one(f"SELECT COUNT(*) AS count FROM audit_logs WHERE {where}", values)
        total = int(total_row["count"] if total_row else 0)
        items = svc.storage.query_all(
            f"SELECT * FROM audit_logs WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*values, safe_limit, safe_offset],
        )
        for item in items:
            item_user_id = item.get("user_id")
            actor = svc.storage.get_by_id("users", item_user_id) if isinstance(item_user_id, str) else None
            item["user_display_name"] = actor.get("display_name") if actor else None
        return {"items": items, "limit": safe_limit, "offset": safe_offset, "total": total}

    @app.get("/api/notifications")
    def notifications(
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        safe_limit, safe_offset = min(max(limit, 1), 200), max(offset, 0)
        unread = " AND read_at IS NULL" if unread_only else ""
        values = [context.tenant_id, context.user_id]
        where = f"tenant_id = ? AND (user_id IS NULL OR user_id = ?){unread}"
        total_row = svc.storage.query_one(f"SELECT COUNT(*) AS count FROM notifications WHERE {where}", values)
        total = int(total_row["count"] if total_row else 0)
        items = svc.storage.query_all(f"SELECT * FROM notifications WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?", [*values, safe_limit, safe_offset])
        unread_row = svc.storage.query_one("SELECT COUNT(*) AS count FROM notifications WHERE tenant_id = ? AND (user_id IS NULL OR user_id = ?) AND read_at IS NULL", values)
        unread_count = int(unread_row["count"] if unread_row else 0)
        return {"items": items, "limit": safe_limit, "offset": safe_offset, "total": total, "unread_count": unread_count}

    @app.post("/api/notifications/{notification_id}/read")
    def read_notification(
        notification_id: str,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        notification = svc.storage.get_by_id("notifications", notification_id, tenant_id=context.tenant_id)
        if not notification or notification.get("user_id") not in {None, context.user_id}:
            raise PermissionError("notification not found")
        return svc.storage.update_by_id("notifications", notification_id, {"read_at": utc_now()}, tenant_id=context.tenant_id) or notification

    @app.post("/api/notifications/read-all")
    def read_all_notifications(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, int]:
        svc.storage.execute(
            "UPDATE notifications SET read_at = ? WHERE tenant_id = ? AND (user_id IS NULL OR user_id = ?) AND read_at IS NULL",
            [utc_now(), context.tenant_id, context.user_id],
        )
        return {"updated": 1}

    @app.get("/api/admin/tenants")
    def admin_tenants(
        limit: int = 50,
        offset: int = 0,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        return svc.system_admin.list_tenants(context.user_id, limit=min(max(limit, 1), 200), offset=max(offset, 0))

    @app.get("/api/admin/tenants/{tenant_id}")
    def admin_tenant(tenant_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.system_admin.tenant_detail(context.user_id, tenant_id)

    @app.patch("/api/admin/tenants/{tenant_id}/subscription")
    def admin_subscription(
        tenant_id: str,
        payload: UpdateSubscriptionRequest,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        return svc.system_admin.update_subscription(context.user_id, tenant_id, payload.model_dump(exclude_none=True))

    @app.get("/api/admin/plans")
    def admin_plans(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        svc.system_admin.require(context.user_id)
        return svc.storage.list("plans", limit=200, order_by=["code"])

    @app.post("/api/admin/plans")
    def admin_create_plan(payload: CreatePlanRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        data = payload.model_dump(exclude_unset=True)
        return svc.system_admin.create_plan(context.user_id, {"status": "active", "allow_scheduler": False, "allow_multi_keyword": False, "allow_advanced_reports": False, **data})

    @app.patch("/api/admin/plans/{plan_id}")
    def admin_update_plan(plan_id: str, payload: UpdatePlanRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.system_admin.update_plan(context.user_id, plan_id, payload.model_dump(exclude_unset=True))

    @app.get("/api/admin/system/usage")
    def admin_system_usage(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.system_admin.system_usage(context.user_id)

    app.include_router(auth_router)
    app.include_router(platform_accounts_router)
    app.include_router(campaigns_router)
    app.include_router(leads_router)
    app.include_router(executions_router)
    app.include_router(build_system_router(config, get_service, require_context))
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
