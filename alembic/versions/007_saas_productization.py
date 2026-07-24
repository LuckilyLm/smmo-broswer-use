"""SaaS productization and tenant administration

Revision ID: 007_saas_productization
Revises: 006_prod_hardening
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa


revision = "007_saas_productization"
down_revision = "006_prod_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("timezone", sa.String(length=100), nullable=True))
    op.execute("UPDATE tenants SET timezone = 'UTC' WHERE timezone IS NULL")
    op.add_column("users", sa.Column("is_system_admin", sa.Boolean(), nullable=True))
    op.execute("UPDATE users SET is_system_admin = false WHERE is_system_admin IS NULL")
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("tenants") as batch:
            batch.alter_column("timezone", existing_type=sa.String(length=100), nullable=False)
        with op.batch_alter_table("users") as batch:
            batch.alter_column("is_system_admin", existing_type=sa.Boolean(), nullable=False)
    else:
        op.alter_column("tenants", "timezone", nullable=False)
        op.alter_column("users", "is_system_admin", nullable=False)

    op.create_table(
        "plans",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("max_users", sa.Integer()),
        sa.Column("max_platform_accounts", sa.Integer()),
        sa.Column("max_campaigns", sa.Integer()),
        sa.Column("max_monthly_executions", sa.Integer()),
        sa.Column("max_monthly_tokens", sa.Integer()),
        sa.Column("max_monthly_leads", sa.Integer()),
        sa.Column("allow_scheduler", sa.Boolean(), nullable=False),
        sa.Column("allow_multi_keyword", sa.Boolean(), nullable=False),
        sa.Column("allow_advanced_reports", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_plans_code"),
    )
    op.create_table(
        "tenant_subscriptions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", sa.String(length=64), sa.ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True)),
        sa.Column("current_period_start", sa.DateTime(timezone=True)),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("overrides_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_subscriptions_tenant"),
    )
    op.create_index("ix_subscriptions_tenant_status", "tenant_subscriptions", ["tenant_id", "status"])
    op.create_table(
        "tenant_invitations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invited_by_user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("accepted_by_user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_tenant_invitations_token_hash"),
    )
    op.create_index("ix_invitations_tenant_status", "tenant_invitations", ["tenant_id", "status"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id", ondelete="SET NULL")),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=64)),
        sa.Column("ip_address", sa.String(length=64)),
        sa.Column("user_agent", sa.Text()),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_tenant_created", "audit_logs", ["tenant_id", "created_at"])
    op.create_index("ix_audit_tenant_action", "audit_logs", ["tenant_id", "action"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resource_type", sa.String(length=100)),
        sa.Column("resource_id", sa.String(length=64)),
        sa.Column("dedupe_key", sa.String(length=255)),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "dedupe_key", name="uq_notifications_tenant_dedupe"),
    )
    op.create_index("ix_notifications_tenant_created", "notifications", ["tenant_id", "created_at"])
    op.create_index("ix_notifications_tenant_read", "notifications", ["tenant_id", "read_at"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("audit_logs")
    op.drop_table("tenant_invitations")
    op.drop_table("tenant_subscriptions")
    op.drop_table("plans")
    op.drop_column("users", "is_system_admin")
    op.drop_column("tenants", "timezone")
