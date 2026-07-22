from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.facebook_leads.saas.scheduler import CampaignScheduler
from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    args = parser.parse_args()

    service = SaaSService(SaaSStorage(os.getenv("DATABASE_URL"), create_schema=False))
    scheduler = CampaignScheduler(service)
    while True:
        scheduler.tick()
        if args.once:
            return
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
