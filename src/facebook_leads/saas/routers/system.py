from __future__ import annotations

from collections.abc import Callable

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
        return {
            "database": "ok" if svc.storage.ping() else "error",
            "worker": bool(worker),
            "scheduler": bool(scheduler),
            "runtime": config.runtime_capabilities(),
            "llm_configured": bool(config.llm_endpoint and config.llm_api_key and config.llm_model),
        }

    return router
