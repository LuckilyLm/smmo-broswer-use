from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

from src.facebook_leads.saas.db import metadata
from src.facebook_leads.saas.storage import SaaSStorage


def test_sqlalchemy_metadata_has_no_foreign_keys() -> None:
    assert sum(len(table.foreign_keys) for table in metadata.tables.values()) == 0


def test_sqlite_create_all_schema_has_no_foreign_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.sqlite"
    SaaSStorage(db_path)

    assert _sqlite_foreign_key_count(db_path) == 0


def test_alembic_head_sqlite_schema_has_no_foreign_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "alembic-head.sqlite"
    database_url = f"sqlite:///{db_path.as_posix()}"
    env = {**os.environ, "DATABASE_URL": database_url}

    subprocess.run(
        ["py", "-3", "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=Path(__file__).resolve().parents[2],
        env=env,
    )

    assert _sqlite_foreign_key_count(db_path) == 0


def _sqlite_foreign_key_count(db_path: Path) -> int:
    with sqlite3.connect(db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return sum(
            len(conn.execute(f'PRAGMA foreign_key_list("{table_name}")').fetchall())
            for (table_name,) in tables
        )
