"""browser runtime

Revision ID: 002_browser_runtime
Revises: 001_initial_saas_schema
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_browser_runtime"
down_revision = "001_initial_saas_schema"
branch_labels = None
depends_on = None


def json_type():
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column("platform_accounts", sa.Column("browser_runtime_id", sa.String(64), nullable=True))
    op.add_column("platform_accounts", sa.Column("login_status", sa.String(50), nullable=False, server_default="unknown"))
    op.add_column("platform_accounts", sa.Column("last_login_check_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("platform_accounts", sa.Column("last_connection_error", sa.Text(), nullable=True))
    op.add_column("platform_accounts", sa.Column("connection_metadata", json_type(), nullable=False, server_default=sa.text("'{}'")))
    op.create_table(
        "browser_runtimes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform_account_id", sa.String(64), sa.ForeignKey("platform_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("runtime_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("profile_path", sa.Text(), nullable=False),
        sa.Column("cdp_port", sa.Integer(), nullable=False),
        sa.Column("cdp_url", sa.String(255), nullable=False),
        sa.Column("browser_pid", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("platform_account_id", name="uq_browser_runtimes_platform_account"),
        sa.UniqueConstraint("cdp_port", name="uq_browser_runtimes_cdp_port"),
    )
    op.create_index("ix_browser_runtimes_tenant_account", "browser_runtimes", ["tenant_id", "platform_account_id"])
    op.create_index("ix_browser_runtimes_tenant_status", "browser_runtimes", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_browser_runtimes_tenant_status", table_name="browser_runtimes")
    op.drop_index("ix_browser_runtimes_tenant_account", table_name="browser_runtimes")
    op.drop_table("browser_runtimes")
    op.drop_column("platform_accounts", "connection_metadata")
    op.drop_column("platform_accounts", "last_connection_error")
    op.drop_column("platform_accounts", "last_login_check_at")
    op.drop_column("platform_accounts", "login_status")
    op.drop_column("platform_accounts", "browser_runtime_id")
