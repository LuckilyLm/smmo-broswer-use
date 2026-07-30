from __future__ import annotations

from collections.abc import Callable
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import APIRouter, Depends

from ..config import ProductionConfig
from ..models import TenantContext
from ..service import SaaSService


def build_system_router(
    config: ProductionConfig,
    get_service: Callable[[], SaaSService],
    require_context: Callable[..., TenantContext],
) -> APIRouter:
    router = APIRouter(prefix="/api/system", tags=["system"])

    @router.get("/runtime-capabilities")
    def runtime_capabilities(_context: TenantContext = Depends(require_context)) -> dict[str, object]:
        return config.runtime_capabilities()

    @router.get("/dependencies")
    def dependencies(
        context: TenantContext = Depends(require_context),
        svc: SaaSService = Depends(get_service),
    ) -> dict[str, object]:
        del context
        worker = svc.storage.find_one("worker_heartbeats", {"status": "online"})
        scheduler = svc.storage.find_one("worker_heartbeats", {"worker_id": "scheduler"})
        runtime_capabilities = config.runtime_capabilities()
        runtime_control = _runtime_control_status(config)
        return {
            "database": "ok" if svc.storage.ping() else "error",
            "worker": bool(worker),
            "scheduler": bool(scheduler),
            "runtime": {
                **runtime_capabilities,
                "browser_runtime_control_url": config.browser_runtime_control_url,
                "browser_runtime_control_reachable": runtime_control["reachable"],
                "browser_runtime_control_status": runtime_control["status"],
            },
            "llm_configured": bool(config.llm_endpoint and config.llm_api_key and config.llm_model),
        }

    return router


def _runtime_control_status(config: ProductionConfig) -> dict[str, object]:
    if config.runtime_host != "remote":
        return {"reachable": config.runtime_available, "status": "local"}
    if not config.browser_runtime_control_url:
        return {"reachable": False, "status": "missing_url"}
    try:
        with urlopen(f"{config.browser_runtime_control_url.rstrip('/')}/health", timeout=2) as response:
            return {"reachable": response.status == 200, "status": "ok" if response.status == 200 else f"http_{response.status}"}
    except (OSError, TimeoutError, URLError):
        return {"reachable": False, "status": "unreachable"}
