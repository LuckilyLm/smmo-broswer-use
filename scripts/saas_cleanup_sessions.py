from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.facebook_leads.saas.config import ProductionConfig
from src.facebook_leads.saas.db import utc_now
from src.facebook_leads.saas.storage import SaaSStorage


def cleanup_sessions(
    storage: SaaSStorage,
    *,
    execute: bool = False,
    inactive_days: int = 30,
) -> dict[str, int | bool]:
    cutoff = utc_now() - timedelta(days=inactive_days)
    candidates = storage.query_all(
        """
        SELECT id
        FROM sessions
        WHERE expires_at <= ?
           OR revoked_at IS NOT NULL
           OR last_seen_at <= ?
        """,
        [utc_now(), cutoff],
    )
    if execute:
        for row in candidates:
            storage.delete_by_id("sessions", row["id"])
    return {"matched": len(candidates), "deleted": len(candidates) if execute else 0, "dry_run": not execute}


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean expired, revoked, or inactive SaaS sessions.")
    parser.add_argument("--execute", action="store_true", help="Delete matching sessions. Default is dry-run.")
    parser.add_argument("--inactive-days", type=int, default=30)
    args = parser.parse_args()
    if args.inactive_days < 1:
        parser.error("--inactive-days must be at least 1")
    config = ProductionConfig.from_env()
    result = cleanup_sessions(
        SaaSStorage(config.database_url, create_schema=False),
        execute=args.execute,
        inactive_days=args.inactive_days,
    )
    print(
        f"dry_run={str(result['dry_run']).lower()} "
        f"matched={result['matched']} deleted={result['deleted']}"
    )


if __name__ == "__main__":
    main()
