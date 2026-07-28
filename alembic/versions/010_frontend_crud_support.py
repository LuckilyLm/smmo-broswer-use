"""Frontend CRUD support without database foreign keys

Revision ID: 010_frontend_crud_support
Revises: 009_remove_database_foreign_keys
Create Date: 2026-07-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "010_frontend_crud_support"
down_revision = "009_remove_database_foreign_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _add_column("campaigns", sa.Column("description", sa.Text()))
    _add_column("campaigns", sa.Column("target_regions_json", sa.JSON(), nullable=True))
    _add_column("campaigns", sa.Column("content_types_json", sa.JSON(), nullable=True))
    _add_column("campaigns", sa.Column("content_language", sa.String(length=20), nullable=True))
    op.execute("UPDATE campaigns SET target_regions_json = '[]' WHERE target_regions_json IS NULL")
    op.execute("UPDATE campaigns SET content_types_json = '[]' WHERE content_types_json IS NULL")
    op.execute("UPDATE campaigns SET content_language = 'any' WHERE content_language IS NULL")

    _add_column("leads", sa.Column("manual_intent_level", sa.String(length=50)))
    _add_column("leads", sa.Column("assigned_user_id", sa.String(length=64)))
    _add_column("leads", sa.Column("contacted_at", sa.DateTime(timezone=True)))
    _add_column("leads", sa.Column("invalid_reason", sa.Text()))
    _add_column("leads", sa.Column("updated_by", sa.String(length=64)))

    op.create_table(
        "lead_notes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("lead_id", sa.String(length=64), nullable=False),
        sa.Column("author_user_id", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_leads_tenant_assigned", "leads", ["tenant_id", "assigned_user_id"])
    op.create_index("ix_leads_tenant_intent", "leads", ["tenant_id", "final_intent_level", "manual_intent_level"])
    op.create_index("ix_lead_notes_tenant_lead", "lead_notes", ["tenant_id", "lead_id"])

    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("campaigns", "target_regions_json", nullable=False)
        op.alter_column("campaigns", "content_types_json", nullable=False)
        op.alter_column("campaigns", "content_language", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_lead_notes_tenant_lead", table_name="lead_notes")
    op.drop_index("ix_leads_tenant_intent", table_name="leads")
    op.drop_index("ix_leads_tenant_assigned", table_name="leads")
    op.drop_table("lead_notes")
    for column in ["updated_by", "invalid_reason", "contacted_at", "assigned_user_id", "manual_intent_level"]:
        op.drop_column("leads", column)
    for column in ["content_language", "content_types_json", "target_regions_json", "description"]:
        op.drop_column("campaigns", column)


def _add_column(table: str, column: sa.Column) -> None:
    op.add_column(table, column)
