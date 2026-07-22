from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.facebook_leads.saas.storage import SaaSStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or migrate the Facebook Leads SaaS database.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--db-path", default=None, help="SQLite compatibility mode for tests only.")
    args = parser.parse_args()
    if args.db_path and not args.database_url:
        storage = SaaSStorage(args.db_path)
        storage.migrate()
        print(f"migrated={storage.engine.url.render_as_string(hide_password=True)}")
        return
    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL or --database-url is required for PostgreSQL migration")
    env = {**os.environ, "DATABASE_URL": database_url}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True)
    print("migrated=alembic_head")


if __name__ == "__main__":
    main()
