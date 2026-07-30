"""Preserve unknown lead reply eligibility.

Revision ID: 011_nullable_reply_allowed
Revises: 010_frontend_crud_support
Create Date: 2026-07-29
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "011_nullable_reply_allowed"
down_revision = "010_frontend_crud_support"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("leads") as batch_op:
        batch_op.alter_column(
            "reply_allowed",
            existing_type=sa.Boolean(),
            nullable=True,
            existing_server_default=None,
        )


def downgrade() -> None:
    op.execute("UPDATE leads SET reply_allowed = false WHERE reply_allowed IS NULL")
    with op.batch_alter_table("leads") as batch_op:
        batch_op.alter_column(
            "reply_allowed",
            existing_type=sa.Boolean(),
            nullable=False,
            existing_server_default=None,
        )
