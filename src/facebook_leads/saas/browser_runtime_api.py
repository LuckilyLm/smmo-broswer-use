from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .config import ProductionConfig
from .models import TenantContext
from .runtime import BrowserRuntimeError, BrowserRuntimeRegistry, safe_runtime
from .storage import SaaSStorage


class RuntimeStartRequest(BaseModel):
    url: str = "https://www.facebook.com/"


class RuntimeResetRequest(BaseModel):
    confirm: str


def create_app(*, config: ProductionConfig | None = None) -> FastAPI:
    config = config or ProductionConfig.from_env()
    storage = SaaSStorage(config.database_url, create_schema=False)
    registry = BrowserRuntimeRegistry(
        storage,
        profiles_root=config.browser_profile_root,
        cdp_port_start=config.browser_cdp_port_start,
        cdp_port_end=config.browser_cdp_port_end,
        runtime_host="local",
        cdp_base_url=config.browser_cdp_base_url,
        cdp_bind_address=config.browser_cdp_bind_address,
        browser_headless=config.browser_headless,
        allow_chrome_discovery=True,
    )
    app = FastAPI(title="SaaS Browser Runtime Control")

    def context(tenant_id: str) -> TenantContext:
        return TenantContext(tenant_id=tenant_id, user_id="browser-runtime", role="system")

    def handle_error(exc: BrowserRuntimeError) -> HTTPException:
        return HTTPException(status_code=400, detail={"error_type": exc.error_type, "message": str(exc)})

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "runtime_host": "local", "cdp_base_url": config.browser_cdp_base_url}

    @app.post("/internal/runtime/{tenant_id}/{account_id}/start")
    def start_runtime(tenant_id: str, account_id: str, payload: RuntimeStartRequest) -> dict[str, Any]:
        try:
            runtime = registry.start_runtime(context(tenant_id), account_id, url=payload.url)
        except BrowserRuntimeError as exc:
            raise handle_error(exc) from exc
        return {"runtime": safe_runtime(runtime)}

    @app.post("/internal/runtime/{tenant_id}/{account_id}/stop")
    def stop_runtime(tenant_id: str, account_id: str) -> dict[str, Any]:
        try:
            runtime = registry.stop_runtime(context(tenant_id), account_id)
        except BrowserRuntimeError as exc:
            raise handle_error(exc) from exc
        return {"runtime": safe_runtime(runtime)}

    @app.post("/internal/runtime/{tenant_id}/{account_id}/restart")
    def restart_runtime(tenant_id: str, account_id: str) -> dict[str, Any]:
        try:
            runtime = registry.restart_runtime(context(tenant_id), account_id)
        except BrowserRuntimeError as exc:
            raise handle_error(exc) from exc
        return {"runtime": safe_runtime(runtime)}

    @app.post("/internal/runtime/{tenant_id}/{account_id}/reset-profile")
    def reset_profile(tenant_id: str, account_id: str, payload: RuntimeResetRequest) -> dict[str, Any]:
        try:
            runtime = registry.reset_profile(context(tenant_id), account_id, confirm=payload.confirm)
        except BrowserRuntimeError as exc:
            raise handle_error(exc) from exc
        return {"runtime": safe_runtime(runtime)}

    @app.post("/internal/runtime/{tenant_id}/{account_id}/check-login")
    async def check_login(tenant_id: str, account_id: str) -> dict[str, Any]:
        try:
            return await registry.check_login(context(tenant_id), account_id)
        except BrowserRuntimeError as exc:
            raise handle_error(exc) from exc

    return app


app = create_app()
