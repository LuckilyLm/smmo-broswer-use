from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.facebook_leads.saas.productization import backfill_legacy_subscriptions, seed_plans
from src.facebook_leads.saas.storage import SaaSStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="Idempotently seed SaaS plans and backfill legacy subscriptions.")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    storage = SaaSStorage(args.database_url, create_schema=False)
    plans = seed_plans(storage)
    backfilled = backfill_legacy_subscriptions(storage)
    print(f"plans={','.join(sorted(plans))}")
    print(f"subscriptions_backfilled={backfilled}")


if __name__ == "__main__":
    main()
