from __future__ import annotations

import os
import hashlib
import hmac
import mimetypes
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn

from dotenv import load_dotenv
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

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
    AssignLeadRequest,
    ChangePasswordRequest,
    BulkCreateKeywordsRequest,
    BulkApproveReplyCandidatesRequest,
    BulkRejectReplyCandidatesRequest,
    BulkUpdateLeadsRequest,
    CreateLeadNoteRequest,
    CreatePlanRequest,
    CreateCampaignRequest,
    CreateKeywordRequest,
    CreatePlatformAccountRequest,
    CreateReplyMatchRuleRequest,
    CreateReplyTemplateRequest,
    InviteMemberRequest,
    LoginRequest,
    PreviewReplyTemplateRequest,
    RejectReplyCandidateRequest,
    ResetProfileRequest,
    ScheduleRequest,
    MarkLeadInvalidRequest,
    TransferOwnershipRequest,
    UpdateMemberRoleRequest,
    UpdatePlanRequest,
    TestReplyMatchRuleRequest,
    UpdateSubscriptionRequest,
    UpdateTenantSettingsRequest,
    UpdateCampaignRequest,
    UpdateKeywordRequest,
    UpdateLeadRequest,
    UpdatePlatformAccountRequest,
    UpdateReplyMatchRuleRequest,
    UpdateReplyCandidateContentRequest,
    UpdateReplyTemplateRequest,
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
            cdp_port_start=config.browser_cdp_port_start,
            cdp_port_end=config.browser_cdp_port_end,
            runtime_host=config.runtime_host,
            cdp_base_url=config.browser_cdp_base_url,
            cdp_bind_address=config.browser_cdp_bind_address,
            remote_control_url=config.browser_runtime_control_url,
            remote_control_secret=config.browser_runtime_control_secret,
            browser_headless=config.browser_headless,
            allow_chrome_discovery=True,
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
        request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}"
        started = time.perf_counter()
        forwarded = request.headers.get("x-forwarded-for", "") if config.trust_proxy else ""
        ip_address = forwarded.split(",", 1)[0].strip() if forwarded else request.client.host if request.client else None
        logger.info(
            "api request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query": str(request.url.query),
                "client_ip": ip_address,
            },
        )
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "api request crashed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "client_ip": ip_address,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                },
            )
            raise
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "api request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "client_ip": ip_address,
            },
        )
        response.headers["x-request-id"] = request_id
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/") and response.status_code < 400:
            authorization = request.headers.get("authorization", "")
            cookie = request.cookies.get(SESSION_COOKIE, "")
            token = _session_token(authorization, cookie, config.session_secret)
            try:
                context = service_instance.context_from_token(token) if token else None
            except PermissionError:
                context = None
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
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = {400: "bad_request", 401: "session_expired", 403: "permission_denied", 404: "not_found", 409: "conflict", 429: "rate_limit_reached", 501: "not_implemented", 503: "service_unavailable"}.get(exc.status_code, "request_failed")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        if isinstance(exc.detail, dict):
            code = str(exc.detail.get("error_type") or exc.detail.get("code") or code)
            message = str(exc.detail.get("message") or message)
        if message == "queue_limit_reached":
            code = "queue_limit_reached"
        logger.warning("api http error", extra={"path": request.url.path, "status_code": exc.status_code, "error_code": code})
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": code, "message": message}})

    @app.exception_handler(BrowserRuntimeError)
    async def browser_runtime_error(request: Request, exc: BrowserRuntimeError) -> JSONResponse:
        status_code = 501 if exc.error_type in {
            "runtime_host_not_implemented",
            "local_browser_runtime_not_supported",
            "browser_runtime_host_unavailable",
        } else 400
        logger.warning("browser runtime error", extra={"path": request.url.path, "status_code": status_code, "error_type": exc.error_type})
        return JSONResponse(status_code=status_code, content={"error": {"code": exc.error_type, "message": str(exc)}})

    @app.exception_handler(PermissionError)
    async def permission_error(request: Request, exc: PermissionError) -> JSONResponse:
        not_found = "not found" in str(exc).lower()
        suspended = str(exc) == "tenant_suspended"
        logger.warning("api permission error", extra={"path": request.url.path, "status_code": 404 if not_found else 403, "error_type": str(exc)})
        return JSONResponse(
            status_code=404 if not_found else 403,
            content={"error": {"code": "not_found" if not_found else "tenant_suspended" if suspended else "permission_denied", "message": "not found" if not_found else str(exc)}},
        )

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError) -> JSONResponse:
        logger.warning("api value error", extra={"path": request.url.path, "status_code": 400, "error_type": str(exc)})
        return JSONResponse(status_code=400, content={"error": {"code": str(exc), "message": str(exc)}})

    @app.exception_handler(ServiceConflictError)
    async def service_conflict(request: Request, exc: ServiceConflictError) -> JSONResponse:
        logger.warning("api service conflict", extra={"path": request.url.path, "status_code": 409, "error_type": str(exc)})
        return JSONResponse(
            status_code=409,
            content={"error": {"code": str(exc), "message": str(exc)}},
        )

    @app.exception_handler(QuotaExceededError)
    async def quota_exceeded(request: Request, exc: QuotaExceededError) -> JSONResponse:
        logger.warning("api quota exceeded", extra={"path": request.url.path, "resource": exc.resource, "limit": exc.limit, "used": exc.used})
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
    async def feature_not_available(request: Request, exc: FeatureNotAvailableError) -> JSONResponse:
        logger.warning("api feature unavailable", extra={"path": request.url.path, "feature": exc.feature})
        return JSONResponse(
            status_code=403,
            content={"error": {"code": "feature_not_available", "message": str(exc), "feature": exc.feature}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        field_errors = [
            {
                "field": ".".join(str(part) for part in error.get("loc", []) if part not in {"body", "query", "path"}),
                "message": str(error.get("msg") or "Invalid value"),
            }
            for error in exc.errors()
        ]
        logger.warning("api validation error", extra={"path": request.url.path, "fields": field_errors})
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "Request validation failed",
                    "fields": [row for row in field_errors if row["field"]],
                }
            },
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("api internal error", extra={"path": request.url.path, "error_type": type(exc).__name__})
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
            allowed_during_password_change = {
                "/api/auth/me",
                "/api/auth/session",
                "/api/auth/change-password",
                "/api/auth/logout",
            }
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

    @auth_router.get("/api/auth/session")
    def session(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.me(context)

    @auth_router.get("/api/auth/sessions")
    def auth_sessions(
        authorization: str = Header(default=""),
        session_cookie: str = Cookie(default="", alias=SESSION_COOKIE),
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        current_token = _session_token(authorization, session_cookie, config.session_secret)
        rows = svc.storage.list(
            "sessions",
            filters={"user_id": context.user_id, "revoked_at": None},
            limit=200,
        )
        items = [_public_session(row, current_token=current_token) for row in rows]
        return {"items": items, "limit": 200, "offset": 0, "total": len(items)}

    @auth_router.delete("/api/auth/sessions/{session_id}", status_code=204)
    def revoke_session(session_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        row = next(
            (
                candidate
                for candidate in svc.storage.list("sessions", filters={"user_id": context.user_id}, limit=1000)
                if hmac.compare_digest(_public_session_id(candidate["id"]), session_id)
            ),
            None,
        )
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        svc.storage.update_by_id("sessions", row["id"], {"revoked_at": utc_now()})
        return Response(status_code=204)

    @auth_router.post("/api/auth/sessions/revoke-others")
    def revoke_other_sessions(
        authorization: str = Header(default=""),
        session_cookie: str = Cookie(default="", alias=SESSION_COOKIE),
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, int]:
        current_token = _session_token(authorization, session_cookie, config.session_secret)
        updated = 0
        for row in svc.storage.list("sessions", filters={"user_id": context.user_id}, limit=1000):
            if row["id"] != current_token and not row.get("revoked_at"):
                svc.storage.update_by_id("sessions", row["id"], {"revoked_at": utc_now()})
                updated += 1
        return {"revoked": updated}

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
    def dashboard(range: str = "7d", context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        days = {"7d": 7, "14d": 14, "30d": 30}.get(range)
        if days is None:
            raise HTTPException(status_code=400, detail="invalid_range")
        return svc.dashboard_summary(context, range_days=days)

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
    def update_platform_account(account_id: str, payload: UpdatePlatformAccountRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            row = svc.update_platform_account(context, account_id, payload.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @platform_accounts_router.delete("/api/platform-accounts/{account_id}", status_code=204)
    def delete_platform_account(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        svc.delete_platform_account(context, account_id)
        return Response(status_code=204)

    @platform_accounts_router.get("/api/platform-accounts/{account_id}")
    def get_platform_account_detail(account_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        account = svc.storage.get_by_id("platform_accounts", account_id, tenant_id=context.tenant_id)
        if not account:
            raise HTTPException(status_code=404, detail="not found")
        runtime = svc.get_platform_runtime(context, account_id)
        recent_executions = svc.storage.query_all(
            "SELECT e.* FROM executions e JOIN campaigns c ON c.id = e.campaign_id WHERE e.tenant_id = ? AND c.platform_account_id = ? ORDER BY e.created_at DESC LIMIT ?",
            [context.tenant_id, account_id, 10],
        )
        recent_errors = [row for row in recent_executions if row.get("error_type") or row.get("status") == "failed"][:5]
        campaign_count = svc.storage.count("campaigns", tenant_id=context.tenant_id, filters={"platform_account_id": account_id, "deleted_at": None})
        active_campaign_count = svc.storage.count("campaigns", tenant_id=context.tenant_id, filters={"platform_account_id": account_id, "status": "active", "deleted_at": None})
        running = runtime and runtime.get("status") == "running"
        return {
            "account": account,
            "runtime": runtime,
            "recent_executions": recent_executions,
            "campaign_count": campaign_count,
            "active_campaign_count": active_campaign_count,
            "recent_errors": recent_errors,
            "capabilities": {
                "can_start": not running,
                "can_stop": bool(running),
                "can_restart": bool(runtime),
                "can_check_login": bool(runtime),
                "can_reset_profile": False,
            },
        }

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
    def list_campaigns(
        request: Request,
        status: str | None = None,
        platform: str | None = None,
        platform_account_id: str | None = None,
        reply_mode: str | None = None,
        search: str | None = None,
        owner_user_id: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> Any:
        safe_limit = min(max(limit, 1), 200)
        filters = {
            "status": status,
            "platform": platform,
            "platform_account_id": platform_account_id,
            "reply_mode": reply_mode,
            "search": search,
            "owner_user_id": owner_user_id,
            "created_from": created_from,
            "created_to": created_to,
        }
        items = svc.list_campaigns(context, filters, limit=safe_limit, offset=max(offset, 0))
        if "limit" not in request.query_params and "offset" not in request.query_params:
            return items
        return {
            "items": items,
            "limit": safe_limit,
            "offset": max(offset, 0),
            "total": svc.count_campaigns(context, filters),
        }

    @campaigns_router.post("/api/campaigns")
    def create_campaign(payload: CreateCampaignRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            data = payload.model_dump(exclude_none=True)
            initial_keywords = data.pop("initial_keywords", None)
            return svc.create_campaign_with_keywords(context, data, initial_keywords)
        except PermissionError as exc:
            raise_resource_permission_error(exc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @campaigns_router.get("/api/campaigns/{campaign_id}")
    def get_campaign(campaign_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.get_campaign_detail(context, campaign_id)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

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
    def create_keyword(campaign_id: str, payload: CreateKeywordRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.create_keyword(context, campaign_id, payload.model_dump(exclude_none=True))
        except PermissionError as exc:
            raise_resource_permission_error(exc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @campaigns_router.post("/api/campaigns/{campaign_id}/keywords/bulk")
    def create_keywords(campaign_id: str, payload: BulkCreateKeywordsRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.create_keywords(context, campaign_id, payload.model_dump(exclude_none=True))
        except PermissionError as exc:
            raise_resource_permission_error(exc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @campaigns_router.patch("/api/keywords/{keyword_id}")
    def update_keyword(keyword_id: str, payload: UpdateKeywordRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        row = svc.update_keyword(context, keyword_id, payload.model_dump(exclude_none=True))
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
        intent_level: str | None = None,
        manual_intent_level: str | None = None,
        assigned_user_id: str | None = None,
        rule_intent_level: str | None = None,
        final_intent_level: str | None = None,
        reply_allowed: bool | None = None,
        keyword: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        search: str | None = None,
        limit: int = 20,
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
                "intent_level": intent_level,
                "manual_intent_level": manual_intent_level,
                "assigned_user_id": assigned_user_id,
                "rule_intent_level": rule_intent_level,
                "final_intent_level": final_intent_level,
                "reply_allowed": reply_allowed,
                "keyword": keyword,
                "created_from": created_from,
                "created_to": created_to,
                "search": search,
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

    @leads_router.patch("/api/leads/{lead_id}")
    def update_lead(lead_id: str, payload: UpdateLeadRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.update_lead(context, lead_id, payload.model_dump(exclude_none=True))
        except PermissionError as exc:
            raise_resource_permission_error(exc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @leads_router.get("/api/leads/{lead_id}/notes")
    def list_lead_notes(lead_id: str, limit: int = 20, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.list_lead_notes(context, lead_id, limit=limit, offset=offset)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @leads_router.post("/api/leads/{lead_id}/notes")
    def create_lead_note(lead_id: str, payload: CreateLeadNoteRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.create_lead_note(context, lead_id, payload.model_dump(exclude_none=True))
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @leads_router.post("/api/leads/{lead_id}/assign")
    def assign_lead(lead_id: str, payload: AssignLeadRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.assign_lead(context, lead_id, payload.assigned_user_id)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @leads_router.post("/api/leads/{lead_id}/mark-contacted")
    def mark_lead_contacted(lead_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.mark_lead_contacted(context, lead_id)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @leads_router.post("/api/leads/{lead_id}/mark-invalid")
    def mark_lead_invalid(lead_id: str, payload: MarkLeadInvalidRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.mark_lead_invalid(context, lead_id, payload.invalid_reason)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @leads_router.post("/api/leads/bulk-update")
    def bulk_update_leads(payload: BulkUpdateLeadsRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            data = payload.model_dump(exclude_none=True)
            lead_ids = data.pop("lead_ids")
            return svc.bulk_update_leads(context, lead_ids, data)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @leads_router.get("/api/leads/{lead_id}/timeline")
    def lead_timeline(lead_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.lead_timeline(context, lead_id)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

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
    def create_reply_template(payload: CreateReplyTemplateRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.create_reply_template(context, payload.model_dump(exclude_none=True))

    @campaigns_router.patch("/api/reply-templates/{template_id}")
    def update_reply_template(template_id: str, payload: UpdateReplyTemplateRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        row = svc.update_reply_template(context, template_id, payload.model_dump(exclude_none=True))
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
    def preview_reply_template(payload: PreviewReplyTemplateRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.preview_reply_template(context, payload.model_dump(exclude_none=True))

    @campaigns_router.get("/api/reply-match-rules")
    def list_reply_match_rules(campaign_id: str | None = None, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> list[dict[str, Any]]:
        return svc.list_reply_match_rules(context, campaign_id=campaign_id)

    @campaigns_router.post("/api/reply-match-rules")
    def create_reply_match_rule(payload: CreateReplyMatchRuleRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.create_reply_match_rule(context, payload.model_dump(exclude_none=True))

    @campaigns_router.patch("/api/reply-match-rules/{rule_id}")
    def update_reply_match_rule(rule_id: str, payload: UpdateReplyMatchRuleRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        row = svc.update_reply_match_rule(context, rule_id, payload.model_dump(exclude_none=True))
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        return row

    @campaigns_router.post("/api/reply-match-rules/{rule_id}/copy")
    def copy_reply_match_rule(rule_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.copy_reply_match_rule(context, rule_id)

    @campaigns_router.delete("/api/reply-match-rules/{rule_id}", status_code=204)
    def delete_reply_match_rule(rule_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        svc.delete_reply_match_rule(context, rule_id)
        return Response(status_code=204)

    @campaigns_router.post("/api/reply-match-rules/test")
    def test_reply_match_rule(payload: TestReplyMatchRuleRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.test_reply_match_rule(context, payload.model_dump(exclude_none=True))

    @campaigns_router.get("/api/reply-candidates")
    def list_reply_candidates(campaign_id: str | None = None, execution_id: str | None = None, reply_plan_id: str | None = None, status: str | None = None, limit: int = 100, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.list_reply_candidates(context, {"campaign_id": campaign_id, "execution_id": execution_id, "reply_plan_id": reply_plan_id, "status": status}, limit=limit, offset=offset)

    @campaigns_router.post("/api/reply-candidates/{candidate_id}/approve")
    def approve_reply_candidate(candidate_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.approve_reply_candidate(context, candidate_id)

    @campaigns_router.post("/api/reply-candidates/{candidate_id}/reject")
    def reject_reply_candidate(candidate_id: str, payload: RejectReplyCandidateRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.reject_reply_candidate(context, candidate_id, payload.reason)

    @campaigns_router.post("/api/reply-candidates/{candidate_id}/cancel")
    def cancel_reply_candidate(candidate_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.cancel_reply_candidate(context, candidate_id)

    @campaigns_router.post("/api/reply-candidates/bulk-approve")
    def bulk_approve_reply_candidates(payload: BulkApproveReplyCandidatesRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.bulk_approve_reply_candidates(context, payload.candidate_ids)

    @campaigns_router.post("/api/reply-candidates/bulk-reject")
    def bulk_reject_reply_candidates(payload: BulkRejectReplyCandidatesRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.bulk_reject_reply_candidates(context, payload.candidate_ids, payload.reason)

    @campaigns_router.patch("/api/reply-candidates/{candidate_id}/content")
    def update_reply_candidate_content(candidate_id: str, payload: UpdateReplyCandidateContentRequest, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        return svc.update_reply_candidate_content(context, candidate_id, payload.rendered_reply_text)

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
    def list_reply_records(
        campaign_id: str | None = None,
        platform_account_id: str | None = None,
        status: str | None = None,
        verified: bool | None = None,
        error_type: str | None = None,
        author_name: str | None = None,
        keyword: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        limit: int = 20,
        offset: int = 0,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        return svc.query_reply_records(
            context,
            {
                "campaign_id": campaign_id,
                "platform_account_id": platform_account_id,
                "status": status,
                "verified": verified,
                "error_type": error_type,
                "author_name": author_name,
                "keyword": keyword,
                "created_from": created_from,
                "created_to": created_to,
            },
            limit=limit,
            offset=offset,
        )

    @campaigns_router.get("/api/reply-records/{record_id}")
    def get_reply_record(record_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.get_reply_record_detail(context, record_id)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

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

    @executions_router.post("/api/executions/{execution_id}/retry")
    def retry_execution(execution_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.retry_execution(context, execution_id)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @executions_router.get("/api/executions/{execution_id}/timeline")
    def execution_timeline(execution_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.execution_timeline(context, execution_id)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @executions_router.get("/api/executions/{execution_id}/artifacts")
    def execution_artifacts(execution_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.execution_artifacts(context, execution_id)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @executions_router.get("/api/executions/{execution_id}/artifacts/{artifact_path:path}")
    def execution_artifact_file(
        execution_id: str,
        artifact_path: str,
        download: bool = False,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> FileResponse:
        try:
            path = svc.execution_artifact_path(context, execution_id, artifact_path)
        except PermissionError as exc:
            raise_resource_permission_error(exc)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid artifact path") from exc
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        disposition = "attachment" if download else "inline"
        return FileResponse(
            path,
            media_type=media_type,
            filename=path.name,
            headers={"Content-Disposition": f'{disposition}; filename="{path.name}"'},
        )

    @executions_router.get("/api/executions/{execution_id}/logs")
    def execution_logs(execution_id: str, limit: int = 100, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.execution_logs(context, execution_id, limit=limit, offset=offset)
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @executions_router.get("/api/executions/{execution_id}/screenshots")
    def execution_screenshots(execution_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.execution_artifacts(context, execution_id, artifact_type="screenshot")
        except PermissionError as exc:
            raise_resource_permission_error(exc)

    @executions_router.get("/api/executions/{execution_id}/token-usage")
    def execution_token_usage(execution_id: str, limit: int = 100, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        try:
            return svc.execution_token_usage(context, execution_id, limit=limit, offset=offset)
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

    @app.get("/api/tenant/members/{membership_id}")
    def member_detail(membership_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        page = svc.tenant_admin.list_members(context, limit=200, offset=0)
        membership = next((row for row in page["items"] if row["id"] == membership_id), None)
        if not membership:
            raise HTTPException(status_code=404, detail="not found")
        user = svc.storage.get_by_id("users", membership["user_id"])
        recent = svc.storage.list("audit_logs", tenant_id=context.tenant_id, filters={"user_id": membership["user_id"]}, limit=10)
        active_sessions = svc.storage.count("sessions", filters={"user_id": membership["user_id"], "revoked_at": None})
        return {"user": _public_api_user(user or {}), "membership": membership, "role": membership["role"], "joined_at": membership.get("created_at"), "last_active_at": None, "active_sessions_count": active_sessions, "recent_audit_actions": recent}

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

    @app.get("/api/tenant/invitations/{invitation_id}")
    def invitation_detail(invitation_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        invitation = svc.storage.get_by_id("tenant_invitations", invitation_id, tenant_id=context.tenant_id)
        if not invitation:
            raise HTTPException(status_code=404, detail="not found")
        return invitation

    @app.post("/api/tenant/invitations/{invitation_id}/resend")
    def resend_invitation(invitation_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        if context.role not in {"owner", "admin"}:
            raise PermissionError("owner or admin role required")
        invitation = svc.storage.get_by_id("tenant_invitations", invitation_id, tenant_id=context.tenant_id)
        if not invitation:
            raise HTTPException(status_code=404, detail="not found")
        if invitation.get("status") != "pending":
            raise ServiceConflictError("invitation_not_pending")
        updated = svc.storage.update_by_id("tenant_invitations", invitation_id, {"expires_at": utc_now() + timedelta(days=7)}, tenant_id=context.tenant_id) or invitation
        svc.audit.record(action="invitation.resend", resource_type="tenant_invitation", resource_id=invitation_id, tenant_id=context.tenant_id, user_id=context.user_id)
        return updated

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
        resource_id: str | None = None,
        result: str | None = None,
        search: str | None = None,
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
        for column, value in (("action", action), ("resource_type", resource_type), ("resource_id", resource_id), ("user_id", user_id)):
            if value:
                clauses.append(f"{column} = ?")
                values.append(value)
        if result:
            clauses.append("CAST(metadata_json AS TEXT) LIKE ?")
            values.append(f"%{result}%")
        if search:
            clauses.append("(LOWER(action) LIKE ? OR LOWER(resource_type) LIKE ? OR LOWER(COALESCE(resource_id, '')) LIKE ?)")
            like = f"%{search.lower()}%"
            values.extend([like, like, like])
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

    @app.get("/api/audit-logs/export")
    def audit_logs_export(
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        user_id: str | None = None,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> Response:
        page = audit_logs(action=action, resource_type=resource_type, resource_id=resource_id, user_id=user_id, limit=200, offset=0, context=context, svc=svc)
        header = ["id", "created_at", "user_id", "action", "resource_type", "resource_id"]
        lines = [",".join(header)]
        for row in page["items"]:
            lines.append(",".join(_csv_cell(row.get(column)) for column in header))
        return Response(content="\n".join(lines), media_type="text/csv")

    @app.get("/api/audit-logs/{audit_id}")
    def audit_log_detail(audit_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        if context.role not in {"owner", "admin"}:
            raise PermissionError("owner or admin role required")
        row = svc.storage.get_by_id("audit_logs", audit_id, tenant_id=context.tenant_id)
        if not row:
            raise HTTPException(status_code=404, detail="not found")
        actor = svc.storage.get_by_id("users", row["user_id"]) if row.get("user_id") else None
        row["user_display_name"] = actor.get("display_name") if actor else None
        return row

    @app.get("/api/notifications")
    def notifications(
        unread_only: bool = False,
        type: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, Any]:
        safe_limit, safe_offset = min(max(limit, 1), 200), max(offset, 0)
        unread = " AND read_at IS NULL" if unread_only else ""
        values = [context.tenant_id, context.user_id]
        where = f"tenant_id = ? AND (user_id IS NULL OR user_id = ?){unread}"
        if type:
            where += " AND type = ?"
            values.append(type)
        if severity:
            where += " AND severity = ?"
            values.append(severity)
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
        before = svc.storage.query_one(
            "SELECT COUNT(*) AS count FROM notifications WHERE tenant_id = ? AND (user_id IS NULL OR user_id = ?) AND read_at IS NULL",
            [context.tenant_id, context.user_id],
        )
        svc.storage.execute(
            "UPDATE notifications SET read_at = ? WHERE tenant_id = ? AND (user_id IS NULL OR user_id = ?) AND read_at IS NULL",
            [utc_now(), context.tenant_id, context.user_id],
        )
        return {"updated": int(before["count"] if before else 0), "unread_count": 0}

    @app.delete("/api/notifications/{notification_id}", status_code=204)
    def delete_notification(notification_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> Response:
        notification = svc.storage.get_by_id("notifications", notification_id, tenant_id=context.tenant_id)
        if not notification or notification.get("user_id") not in {None, context.user_id}:
            raise HTTPException(status_code=404, detail="not found")
        svc.storage.delete_by_id("notifications", notification_id, tenant_id=context.tenant_id)
        return Response(status_code=204)

    @app.post("/api/notifications/clear-read")
    def clear_read_notifications(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, int]:
        before = svc.storage.query_one(
            "SELECT COUNT(*) AS count FROM notifications WHERE tenant_id = ? AND (user_id IS NULL OR user_id = ?) AND read_at IS NOT NULL",
            [context.tenant_id, context.user_id],
        )
        svc.storage.execute(
            "DELETE FROM notifications WHERE tenant_id = ? AND (user_id IS NULL OR user_id = ?) AND read_at IS NOT NULL",
            [context.tenant_id, context.user_id],
        )
        unread = svc.storage.query_one(
            "SELECT COUNT(*) AS count FROM notifications WHERE tenant_id = ? AND (user_id IS NULL OR user_id = ?) AND read_at IS NULL",
            [context.tenant_id, context.user_id],
        )
        return {"deleted": int(before["count"] if before else 0), "unread_count": int(unread["count"] if unread else 0)}

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

    @app.get("/api/admin/users")
    def admin_users(limit: int = 20, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        svc.system_admin.require(context.user_id)
        safe_limit, safe_offset = min(max(limit, 1), 200), max(offset, 0)
        items = [_public_api_user(row) for row in svc.storage.list("users", limit=safe_limit, offset=safe_offset)]
        return {"items": items, "limit": safe_limit, "offset": safe_offset, "total": svc.storage.count("users")}

    @app.get("/api/admin/users/{user_id}")
    def admin_user_detail(user_id: str, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        svc.system_admin.require(context.user_id)
        user = svc.storage.get_by_id("users", user_id)
        if not user:
            raise HTTPException(status_code=404, detail="not found")
        memberships = svc.storage.list("tenant_users", filters={"user_id": user_id}, limit=200)
        sessions = svc.storage.query_all(
            "SELECT id, tenant_id, expires_at, last_seen_at, revoked_at, created_at FROM sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            [user_id, 20],
        )
        return {
            "user": _public_api_user(user),
            "memberships": memberships,
            "sessions": [_public_admin_session(session) for session in sessions],
        }

    @app.get("/api/admin/system/health")
    def admin_system_health(context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        svc.system_admin.require(context.user_id)
        return {
            "api": {"status": "ok"},
            "postgres": {"status": "ok" if svc.storage.ping() else "error"},
            "worker": worker_status(context=context, svc=svc),
            "scheduler": scheduler_status(context=context, svc=svc),
            "queue": svc.storage.queue_counts(tenant_id=context.tenant_id),
            "browser_runtimes": {"count": svc.storage.count("browser_runtimes")},
        }

    @app.get("/api/admin/system/runtimes")
    def admin_system_runtimes(limit: int = 20, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        svc.system_admin.require(context.user_id)
        safe_limit, safe_offset = min(max(limit, 1), 200), max(offset, 0)
        rows = svc.storage.list("browser_runtimes", limit=safe_limit, offset=safe_offset)
        for row in rows:
            row.pop("profile_path", None)
            row.pop("cdp_url", None)
        return {"items": rows, "limit": safe_limit, "offset": safe_offset, "total": svc.storage.count("browser_runtimes")}

    @app.get("/api/admin/system/queue")
    def admin_system_queue(limit: int = 20, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        svc.system_admin.require(context.user_id)
        safe_limit, safe_offset = min(max(limit, 1), 200), max(offset, 0)
        return {
            "items": svc.storage.list("execution_queue_items", limit=safe_limit, offset=safe_offset),
            "limit": safe_limit,
            "offset": safe_offset,
            "total": svc.storage.count("execution_queue_items"),
        }

    @app.get("/api/admin/audit-logs")
    def admin_audit_logs(limit: int = 20, offset: int = 0, context: TenantContext = Depends(require_context), svc: SaaSService = Depends(get_service)) -> dict[str, Any]:
        svc.system_admin.require(context.user_id)
        safe_limit, safe_offset = min(max(limit, 1), 200), max(offset, 0)
        return {
            "items": svc.storage.list("audit_logs", limit=safe_limit, offset=safe_offset),
            "limit": safe_limit,
            "offset": safe_offset,
            "total": svc.storage.count("audit_logs"),
        }

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


def _csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    escaped = text.replace('"', '""')
    return f'"{escaped}"' if any(ch in escaped for ch in [",", "\n", '"']) else escaped


def _public_session_id(raw_token: str) -> str:
    digest = hashlib.sha256(b"leadflow:session-public-id:v1\x00" + raw_token.encode("utf-8")).hexdigest()
    return f"session_{digest}"


def _public_session_metadata(session: dict[str, Any]) -> dict[str, Any]:
    raw_token = str(session["id"])
    return {
        "id": _public_session_id(raw_token),
        "tenant_id": session.get("tenant_id"),
        "created_at": session.get("created_at"),
        "last_seen_at": session.get("last_seen_at"),
        "expires_at": session.get("expires_at"),
    }


def _public_session(session: dict[str, Any], *, current_token: str) -> dict[str, Any]:
    raw_token = str(session["id"])
    return {
        **_public_session_metadata(session),
        "current": bool(current_token) and hmac.compare_digest(raw_token, current_token),
    }


def _public_admin_session(session: dict[str, Any]) -> dict[str, Any]:
    return {
        **_public_session_metadata(session),
        "revoked_at": session.get("revoked_at"),
    }


def _public_api_user(user: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in user.items() if key not in {"password_hash"}}
