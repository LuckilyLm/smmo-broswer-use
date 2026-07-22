from __future__ import annotations

import argparse
import asyncio
import os
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


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args()

    service = SaaSService(SaaSStorage(os.getenv("DATABASE_URL"), create_schema=False))
    worker = ExecutionWorker(service, worker_id=args.worker_id)
    if args.once:
        await worker.tick()
        return
    await worker.run_forever(poll_seconds=args.poll_seconds)


if __name__ == "__main__":
    asyncio.run(main())
