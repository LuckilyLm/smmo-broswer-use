"""initial saas schema

Revision ID: 001_initial_saas_schema
Revises:
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial_saas_schema"
down_revision = None
branch_labels = None
depends_on = None


def json_type():
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("default_target_policy", sa.String(50), nullable=False),
        sa.Column("default_min_confidence", sa.Float(), nullable=False),
        sa.Column("default_daily_limit", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tenant_users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_users_tenant_user"),
    )
    op.create_table(
        "platform_accounts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("external_account_id", sa.String(255)),
        sa.Column("external_account_name", sa.String(255)),
        sa.Column("connection_status", sa.String(50), nullable=False),
        sa.Column("config_json", json_type(), nullable=False),
        sa.Column("secret_ref", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "platform", "external_account_id", name="uq_platform_accounts_tenant_platform_external"),
    )
    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("platform_account_id", sa.String(64), sa.ForeignKey("platform_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("target_policy", sa.String(50), nullable=False),
        sa.Column("max_contents", sa.Integer(), nullable=False),
        sa.Column("max_comments", sa.Integer(), nullable=False),
        sa.Column("min_confidence", sa.Float(), nullable=False),
        sa.Column("max_leads", sa.Integer(), nullable=False),
        sa.Column("daily_limit", sa.Integer(), nullable=False),
        sa.Column("llm_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "campaign_keywords",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(64), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("campaign_id", "keyword", name="uq_campaign_keywords_campaign_keyword"),
    )
    op.create_table(
        "reply_rules",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(64), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("intent_type", sa.String(100)),
        sa.Column("min_confidence", sa.Float(), nullable=False),
        sa.Column("reply_template", sa.Text(), nullable=False),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("approval_mode", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "leads",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(64), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform_account_id", sa.String(64), sa.ForeignKey("platform_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("external_lead_id", sa.String(255)),
        sa.Column("comment_id", sa.String(255)),
        sa.Column("comment_fingerprint", sa.String(255), nullable=False),
        sa.Column("author_name", sa.String(255)),
        sa.Column("author_url", sa.Text()),
        sa.Column("comment_text", sa.Text()),
        sa.Column("source_content_url", sa.Text()),
        sa.Column("direct_comment_url", sa.Text()),
        sa.Column("rule_intent_level", sa.String(50)),
        sa.Column("llm_confidence", sa.Float()),
        sa.Column("llm_intent_level", sa.String(50)),
        sa.Column("llm_intent_types", json_type(), nullable=False),
        sa.Column("llm_reason", sa.Text()),
        sa.Column("suggested_reply", sa.Text()),
        sa.Column("ownership_status", sa.String(50)),
        sa.Column("reply_allowed", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "campaign_id", "comment_fingerprint", name="uq_leads_tenant_campaign_fingerprint"),
    )
    op.create_table(
        "executions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(64), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.String(255)),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("stage", sa.String(100)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("elapsed_ms", sa.Integer()),
        sa.Column("scanned_contents", sa.Integer(), nullable=False),
        sa.Column("scanned_comments", sa.Integer(), nullable=False),
        sa.Column("lead_candidates", sa.Integer(), nullable=False),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("selected_count", sa.Integer(), nullable=False),
        sa.Column("send_disabled", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(255)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "token_usage",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(64), sa.ForeignKey("campaigns.id", ondelete="SET NULL")),
        sa.Column("execution_id", sa.String(64), sa.ForeignKey("executions.id", ondelete="SET NULL")),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(255)),
        sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()),
        sa.Column("total_tokens", sa.Integer()),
        sa.Column("request_count", sa.Integer()),
        sa.Column("estimated_cost", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_leads_tenant_created_at", "leads", ["tenant_id", "created_at"])
    op.create_index("ix_leads_tenant_status", "leads", ["tenant_id", "status"])
    op.create_index("ix_leads_tenant_campaign", "leads", ["tenant_id", "campaign_id"])
    op.create_index("ix_leads_comment_fingerprint", "leads", ["comment_fingerprint"])
    op.create_index("ix_executions_tenant_started_at", "executions", ["tenant_id", "started_at"])
    op.create_index("ix_executions_tenant_campaign", "executions", ["tenant_id", "campaign_id"])
    op.create_index("ix_token_usage_tenant_created_at", "token_usage", ["tenant_id", "created_at"])
    op.create_index("ix_token_usage_tenant_campaign", "token_usage", ["tenant_id", "campaign_id"])
    op.create_index("ix_campaigns_tenant_status", "campaigns", ["tenant_id", "status"])


def downgrade() -> None:
    for index, table in [
        ("ix_campaigns_tenant_status", "campaigns"),
        ("ix_token_usage_tenant_campaign", "token_usage"),
        ("ix_token_usage_tenant_created_at", "token_usage"),
        ("ix_executions_tenant_campaign", "executions"),
        ("ix_executions_tenant_started_at", "executions"),
        ("ix_leads_comment_fingerprint", "leads"),
        ("ix_leads_tenant_campaign", "leads"),
        ("ix_leads_tenant_status", "leads"),
        ("ix_leads_tenant_created_at", "leads"),
    ]:
        op.drop_index(index, table_name=table)
    for table in ["sessions", "token_usage", "executions", "leads", "reply_rules", "campaign_keywords", "campaigns", "platform_accounts", "tenant_users", "users", "tenants"]:
        op.drop_table(table)
