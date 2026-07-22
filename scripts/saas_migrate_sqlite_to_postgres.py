from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.facebook_leads.saas.storage import SaaSStorage


TABLES = [
    "tenants",
    "users",
    "tenant_users",
    "platform_accounts",
    "browser_runtimes",
    "campaigns",
    "campaign_keywords",
    "reply_rules",
    "leads",
    "executions",
    "token_usage",
    "sessions",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Phase 7.0 SaaS SQLite data to PostgreSQL.")
    parser.add_argument("--sqlite-path", required=True)
    parser.add_argument("--postgres-url", required=True)
    parser.add_argument("--allow-non-empty", action="store_true")
    parser.add_argument("--skip-sessions", action="store_true")
    args = parser.parse_args()

    source_counts = sqlite_counts(args.sqlite_path)
    target = SaaSStorage(args.postgres_url, create_schema=False)
    tables = [table for table in TABLES if not (args.skip_sessions and table == "sessions")]
    target_counts_before = target.table_counts(tables)
    if any(target_counts_before.values()) and not args.allow_non_empty:
        raise SystemExit("target PostgreSQL database is not empty; rerun with --allow-non-empty only if merge risk is acceptable")

    rows_by_table = sqlite_rows(args.sqlite_path, tables)
    for table in tables:
        for row in rows_by_table[table]:
            if target.get_by_id(table, row["id"]):
                continue
            target.insert(table, row)
    target_counts_after = target.table_counts(tables)

    print("table,sqlite_before,postgres_before,postgres_after")
    for table in tables:
        print(f"{table},{source_counts.get(table, 0)},{target_counts_before.get(table, 0)},{target_counts_after.get(table, 0)}")


def sqlite_counts(path: str) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
        return {table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in TABLES if table_exists(connection, table)}


def sqlite_rows(path: str, tables: list[str]) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = {}
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        for table in tables:
            if not table_exists(connection, table):
                output[table] = []
                continue
            output[table] = [dict(row) for row in connection.execute(f"SELECT * FROM {table}").fetchall()]
    return output


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", [table]).fetchone()
    return bool(row)


if __name__ == "__main__":
    main()
