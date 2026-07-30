from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.facebook_leads.saas.seed import demo_readiness_summary, seed_demo_data
from src.facebook_leads.saas.storage import SaaSStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely seed or inspect the Facebook Leads demo tenant.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--db-path", default=None, help="SQLite compatibility mode for local demos/tests only.")
    parser.add_argument("--password", default=None, help="Demo user password; prefer FACEBOOK_LEADS_DEMO_PASSWORD.")
    parser.add_argument("--summary", action="store_true", help="Only report demo readiness; make no changes.")
    args = parser.parse_args()
    if args.summary:
        storage = SaaSStorage(args.database_url or args.db_path)
        summary = demo_readiness_summary(storage)
    else:
        if os.getenv("SAAS_ENABLE_DEMO_SEED", "false").lower() != "true":
            raise SystemExit("Demo seed is disabled; set SAAS_ENABLE_DEMO_SEED=true explicitly")
        storage = SaaSStorage(args.database_url or args.db_path)
        summary = seed_demo_data(storage, password=args.password)["readiness"]
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not summary["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
