from __future__ import annotations

import argparse
import sys
import signal
import threading
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.facebook_leads.saas.scheduler import CampaignScheduler
from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage
from src.facebook_leads.saas.logging import configure_logging
from src.facebook_leads.saas.config import ProductionConfig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    args = parser.parse_args()

    config = ProductionConfig.from_env()
    service = SaaSService(
        SaaSStorage(config.database_url, create_schema=False),
        max_queued_executions_per_tenant=config.max_queued_executions_per_tenant,
        session_ttl_hours=config.session_ttl_hours,
        session_idle_timeout_hours=config.session_idle_timeout_hours,
        config=config,
    )
    scheduler = CampaignScheduler(service, queue_full_retry_minutes=config.scheduler_queue_full_retry_minutes)
    logger = configure_logging("scheduler", config.log_level)
    stop_event = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_args: stop_event.set())
    signal.signal(signal.SIGINT, lambda *_args: stop_event.set())
    while not stop_event.is_set():
        try:
            scheduler.tick()
        except Exception as exc:
            scheduler.record_error(type(exc).__name__)
            logger.error("scheduler tick failed")
        if args.once:
            return
        stop_event.wait(args.poll_seconds)
    logger.info("scheduler stopped")


if __name__ == "__main__":
    main()
