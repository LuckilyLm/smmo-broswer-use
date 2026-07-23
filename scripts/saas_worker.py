from __future__ import annotations

import argparse
import asyncio
import os
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


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args()

    service = SaaSService(SaaSStorage(os.getenv("DATABASE_URL"), create_schema=False))
    service.runtime_registry.reconcile_all()
    concurrency = int(os.getenv("SAAS_WORKER_CONCURRENCY", "1"))
    logger = configure_logging("worker", os.getenv("LOG_LEVEL", "INFO"))
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signal_name, stop_event.set)
        except NotImplementedError:
            signal.signal(signal_name, lambda *_args: loop.call_soon_threadsafe(stop_event.set))
    base_id = args.worker_id or "worker"
    workers = [ExecutionWorker(service, worker_id=base_id if concurrency == 1 else f"{base_id}-{index + 1}") for index in range(concurrency)]
    logger.info("worker pool started")
    if args.once:
        await workers[0].tick()
        return
    await asyncio.gather(*(worker.run_forever(poll_seconds=args.poll_seconds, stop_event=stop_event) for worker in workers))
    logger.info("worker pool stopped")


if __name__ == "__main__":
    asyncio.run(main())
