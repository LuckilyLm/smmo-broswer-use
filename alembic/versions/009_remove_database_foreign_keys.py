"""Remove database foreign key constraints

Revision ID: 009_remove_database_foreign_keys
Revises: 008_reply_automation
Create Date: 2026-07-24
"""
from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op


revision = "009_remove_database_foreign_keys"
down_revision = "008_reply_automation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        _drop_sqlite_foreign_keys(bind)
        return

    inspector = sa.inspect(bind)
    for table_name in inspector.get_table_names():
        for foreign_key in inspector.get_foreign_keys(table_name):
            name = foreign_key.get("name")
            if name:
                op.drop_constraint(name, table_name, type_="foreignkey")


def downgrade() -> None:
    # Database-level foreign keys are intentionally forbidden for this project.
    # Association integrity is enforced in the service layer.
    return None


def _drop_sqlite_foreign_keys(bind: sa.engine.Connection) -> None:
    tables = [
        row[0]
        for row in bind.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
        )
    ]
    bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        for table_name in tables:
            if not bind.exec_driver_sql(f'PRAGMA foreign_key_list("{table_name}")').fetchall():
                continue
            create_sql = bind.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?",
                (table_name,),
            ).scalar()
            if not create_sql:
                continue
            replacement_sql = re.sub(
                rf"^CREATE TABLE\s+\"?{re.escape(table_name)}\"?",
                f'CREATE TABLE "{table_name}__nofk"',
                _remove_foreign_key_clauses(create_sql),
                count=1,
                flags=re.IGNORECASE,
            )
            if replacement_sql == create_sql:
                continue
            columns = [
                row[1]
                for row in bind.exec_driver_sql(f'PRAGMA table_info("{table_name}")')
            ]
            quoted_columns = ", ".join(f'"{column}"' for column in columns)
            bind.exec_driver_sql(replacement_sql)
            bind.exec_driver_sql(
                f'INSERT INTO "{table_name}__nofk" ({quoted_columns}) SELECT {quoted_columns} FROM "{table_name}"'
            )
            bind.exec_driver_sql(f'DROP TABLE "{table_name}"')
            bind.exec_driver_sql(f'ALTER TABLE "{table_name}__nofk" RENAME TO "{table_name}"')
    finally:
        bind.exec_driver_sql("PRAGMA foreign_keys=ON")


def _remove_foreign_key_clauses(create_sql: str) -> str:
    lines = create_sql.splitlines()
    cleaned: list[str] = []
    for line in lines:
        if re.search(r"\bFOREIGN KEY\b|\bREFERENCES\b", line, re.IGNORECASE):
            if cleaned and cleaned[-1].rstrip().endswith(","):
                cleaned[-1] = cleaned[-1].rstrip().rstrip(",")
            continue
        cleaned.append(line)
    return "\n".join(cleaned)
