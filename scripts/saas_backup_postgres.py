from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a PostgreSQL custom-format schema and data backup.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--output-dir", type=Path, default=Path("backups/postgres"))
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"saas-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.dump"
    subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--file", str(output), args.database_url], check=True)
    print(f"backup={output}")


if __name__ == "__main__":
    main()
