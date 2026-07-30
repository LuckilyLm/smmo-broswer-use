from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage
from src.facebook_leads.saas.worker import ExecutionWorker
from src.facebook_leads.saas.logging import configure_logging
from src.facebook_leads.saas.config import ProductionConfig
from src.facebook_leads.saas.runtime import BrowserRuntimeRegistry


def build_worker_service(config: ProductionConfig | None = None) -> SaaSService:
    config = config or ProductionConfig.from_env()
    if not config.runtime_available:
        raise RuntimeError("browser_runtime_host_unavailable")
    storage = SaaSStorage(config.database_url, create_schema=False)
    registry = BrowserRuntimeRegistry(
        storage,
        profiles_root=config.browser_profile_root,
        cdp_port_start=config.browser_cdp_port_start,
        cdp_port_end=config.browser_cdp_port_end,
        runtime_host=config.runtime_host,
        cdp_base_url=config.browser_cdp_base_url,
        cdp_bind_address=config.browser_cdp_bind_address,
        remote_control_url=config.browser_runtime_control_url,
        browser_headless=config.browser_headless,
        allow_chrome_discovery=True,
    )
    return SaaSService(
        storage,
        runtime_registry=registry,
        max_queued_executions_per_tenant=config.max_queued_executions_per_tenant,
        session_ttl_hours=config.session_ttl_hours,
        session_idle_timeout_hours=config.session_idle_timeout_hours,
        config=config,
    )


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args()

    config = ProductionConfig.from_env()
    service = build_worker_service(config)
    service.runtime_registry.reconcile_all()
    concurrency = config.worker_concurrency
    logger = configure_logging("worker", config.log_level)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signal_name, stop_event.set)
        except NotImplementedError:
            signal.signal(signal_name, lambda *_args: loop.call_soon_threadsafe(stop_event.set))
    base_id = args.worker_id or "worker"
    workers = [
        ExecutionWorker(
            service,
            worker_id=base_id if concurrency == 1 else f"{base_id}-{index + 1}",
            heartbeat_interval_seconds=config.worker_heartbeat_interval_seconds,
            queue_stale_seconds=config.queue_stale_seconds,
            heartbeat_stale_seconds=config.heartbeat_stale_seconds,
        )
        for index in range(concurrency)
    ]
    logger.info("worker pool started")
    if args.once:
        await workers[0].tick()
        return
    await asyncio.gather(*(worker.run_forever(poll_seconds=args.poll_seconds, stop_event=stop_event) for worker in workers))
    logger.info("worker pool stopped")


if __name__ == "__main__":
    asyncio.run(main())
