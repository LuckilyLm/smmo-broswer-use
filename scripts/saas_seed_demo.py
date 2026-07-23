from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.facebook_leads.saas.seed import seed_demo_data
from src.facebook_leads.saas.storage import SaaSStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo tenant data for the Facebook Leads SaaS API.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--db-path", default=None, help="SQLite compatibility mode for tests only.")
    args = parser.parse_args()
    if os.getenv("SAAS_ENABLE_DEMO_SEED", "false").lower() != "true":
        raise SystemExit("Demo seed is disabled; set SAAS_ENABLE_DEMO_SEED=true explicitly")
    seeded = seed_demo_data(SaaSStorage(args.database_url or args.db_path))
    print(f"tenant_id={seeded['tenant']['id']}")
    print(f"campaign_id={seeded['campaign']['id']}")
    print("demo_email=admin@example.com")


if __name__ == "__main__":
    main()
