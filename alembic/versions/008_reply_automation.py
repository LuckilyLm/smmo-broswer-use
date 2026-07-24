"""User-configured reply automation workflow

Revision ID: 008_reply_automation
Revises: 007_saas_productization
Create Date: 2026-07-24
"""
from alembic import op
import sqlalchemy as sa


revision = "008_reply_automation"
down_revision = "007_saas_productization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _add_column("tenants", sa.Column("default_whatsapp", sa.String(length=255)))
    _add_column("tenants", sa.Column("default_email", sa.String(length=255)))
    _add_column("tenants", sa.Column("default_website", sa.String(length=500)))
    _add_column("tenants", sa.Column("default_contact_text", sa.Text()))
    _add_column("tenants", sa.Column("tenant_reply_enabled", sa.Boolean(), nullable=True))
    op.execute("UPDATE tenants SET tenant_reply_enabled = false WHERE tenant_reply_enabled IS NULL")

    _add_column("campaigns", sa.Column("lead_detection_mode", sa.String(length=50), nullable=True))
    _add_column("campaigns", sa.Column("reply_mode", sa.String(length=50), nullable=True))
    _add_column("campaigns", sa.Column("default_reply_template_id", sa.String(length=64)))
    _add_column("campaigns", sa.Column("positive_keywords_json", sa.JSON(), nullable=True))
    _add_column("campaigns", sa.Column("negative_keywords_json", sa.JSON(), nullable=True))
    _add_column("campaigns", sa.Column("excluded_authors_json", sa.JSON(), nullable=True))
    _add_column("campaigns", sa.Column("excluded_comment_patterns_json", sa.JSON(), nullable=True))
    _add_column("campaigns", sa.Column("default_whatsapp", sa.String(length=255)))
    _add_column("campaigns", sa.Column("default_email", sa.String(length=255)))
    _add_column("campaigns", sa.Column("default_website", sa.String(length=500)))
    _add_column("campaigns", sa.Column("default_contact_text", sa.Text()))
    _add_column("campaigns", sa.Column("reply_daily_limit", sa.Integer(), nullable=True))
    _add_column("campaigns", sa.Column("reply_per_minute_limit", sa.Integer(), nullable=True))
    _add_column("campaigns", sa.Column("reply_per_hour_limit", sa.Integer(), nullable=True))
    _add_column("campaigns", sa.Column("reply_min_interval_seconds", sa.Integer(), nullable=True))
    op.execute("UPDATE campaigns SET lead_detection_mode = 'rules_only' WHERE lead_detection_mode IS NULL")
    op.execute("UPDATE campaigns SET reply_mode = 'disabled' WHERE reply_mode IS NULL")
    op.execute("UPDATE campaigns SET positive_keywords_json = '[]' WHERE positive_keywords_json IS NULL")
    op.execute("UPDATE campaigns SET negative_keywords_json = '[]' WHERE negative_keywords_json IS NULL")
    op.execute("UPDATE campaigns SET excluded_authors_json = '[]' WHERE excluded_authors_json IS NULL")
    op.execute("UPDATE campaigns SET excluded_comment_patterns_json = '[]' WHERE excluded_comment_patterns_json IS NULL")
    op.execute("UPDATE campaigns SET reply_daily_limit = 30 WHERE reply_daily_limit IS NULL")
    op.execute("UPDATE campaigns SET reply_per_minute_limit = 1 WHERE reply_per_minute_limit IS NULL")
    op.execute("UPDATE campaigns SET reply_per_hour_limit = 10 WHERE reply_per_hour_limit IS NULL")
    op.execute("UPDATE campaigns SET reply_min_interval_seconds = 60 WHERE reply_min_interval_seconds IS NULL")

    op.create_table(
        "reply_templates",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "reply_match_rules",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(length=64), sa.ForeignKey("campaigns.id", ondelete="CASCADE")),
        sa.Column("reply_template_id", sa.String(length=64), sa.ForeignKey("reply_templates.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("contains_any_json", sa.JSON(), nullable=False),
        sa.Column("contains_all_json", sa.JSON(), nullable=False),
        sa.Column("exact_text", sa.Text()),
        sa.Column("regex_pattern", sa.Text()),
        sa.Column("author_exclude_json", sa.JSON(), nullable=False),
        sa.Column("comment_language", sa.String(length=20)),
        sa.Column("minimum_length", sa.Integer()),
        sa.Column("maximum_length", sa.Integer()),
        sa.Column("created_by", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "reply_plans",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(length=64), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("execution_id", sa.String(length=64), sa.ForeignKey("executions.id", ondelete="CASCADE")),
        sa.Column("platform_account_id", sa.String(length=64), sa.ForeignKey("platform_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("reply_mode", sa.String(length=50), nullable=False),
        sa.Column("total_candidates", sa.Integer(), nullable=False),
        sa.Column("approved_count", sa.Integer(), nullable=False),
        sa.Column("sent_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("blocked_reason", sa.String(length=255)),
        sa.Column("created_by", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_by", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "reply_candidates",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(length=64), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("execution_id", sa.String(length=64), sa.ForeignKey("executions.id", ondelete="CASCADE")),
        sa.Column("reply_plan_id", sa.String(length=64), sa.ForeignKey("reply_plans.id", ondelete="CASCADE")),
        sa.Column("platform_account_id", sa.String(length=64), sa.ForeignKey("platform_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("comment_id", sa.String(length=255)),
        sa.Column("comment_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("author_name", sa.String(length=255)),
        sa.Column("comment_text", sa.Text()),
        sa.Column("source_content_url", sa.Text()),
        sa.Column("direct_comment_url", sa.Text()),
        sa.Column("matched_rule_id", sa.String(length=64)),
        sa.Column("matched_rule_name", sa.String(length=255)),
        sa.Column("reply_template_id", sa.String(length=64)),
        sa.Column("rendered_reply_text", sa.Text()),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("blocked_reason", sa.String(length=255)),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("approved_by", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("rejected_by", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("rejected_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "campaign_id", "idempotency_key", name="uq_reply_candidates_tenant_campaign_key"),
    )
    op.create_table(
        "reply_records",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reply_candidate_id", sa.String(length=64), sa.ForeignKey("reply_candidates.id", ondelete="SET NULL")),
        sa.Column("reply_plan_id", sa.String(length=64), sa.ForeignKey("reply_plans.id", ondelete="SET NULL")),
        sa.Column("campaign_id", sa.String(length=64), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform_account_id", sa.String(length=64), sa.ForeignKey("platform_accounts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("comment_id", sa.String(length=255)),
        sa.Column("reply_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(length=255)),
        sa.Column("error_message", sa.Text()),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_reply_records_tenant_key"),
    )
    op.create_index("ix_reply_templates_tenant", "reply_templates", ["tenant_id", "enabled"])
    op.create_index("ix_reply_match_rules_tenant_campaign", "reply_match_rules", ["tenant_id", "campaign_id"])
    op.create_index("ix_reply_candidates_tenant_status", "reply_candidates", ["tenant_id", "status"])
    op.create_index("ix_reply_plans_tenant_status", "reply_plans", ["tenant_id", "status"])
    op.create_index("ix_reply_records_tenant_created", "reply_records", ["tenant_id", "created_at"])

    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("tenants", "tenant_reply_enabled", nullable=False)
        for column in [
            "lead_detection_mode",
            "reply_mode",
            "positive_keywords_json",
            "negative_keywords_json",
            "excluded_authors_json",
            "excluded_comment_patterns_json",
            "reply_daily_limit",
            "reply_per_minute_limit",
            "reply_per_hour_limit",
            "reply_min_interval_seconds",
        ]:
            op.alter_column("campaigns", column, nullable=False)


def downgrade() -> None:
    op.drop_index("ix_reply_records_tenant_created", table_name="reply_records")
    op.drop_index("ix_reply_plans_tenant_status", table_name="reply_plans")
    op.drop_index("ix_reply_candidates_tenant_status", table_name="reply_candidates")
    op.drop_index("ix_reply_match_rules_tenant_campaign", table_name="reply_match_rules")
    op.drop_index("ix_reply_templates_tenant", table_name="reply_templates")
    op.drop_table("reply_records")
    op.drop_table("reply_candidates")
    op.drop_table("reply_plans")
    op.drop_table("reply_match_rules")
    op.drop_table("reply_templates")
    for column in [
        "reply_min_interval_seconds",
        "reply_per_hour_limit",
        "reply_per_minute_limit",
        "reply_daily_limit",
        "default_contact_text",
        "default_website",
        "default_email",
        "default_whatsapp",
        "excluded_comment_patterns_json",
        "excluded_authors_json",
        "negative_keywords_json",
        "positive_keywords_json",
        "default_reply_template_id",
        "reply_mode",
        "lead_detection_mode",
    ]:
        op.drop_column("campaigns", column)
    for column in ["tenant_reply_enabled", "default_contact_text", "default_website", "default_email", "default_whatsapp"]:
        op.drop_column("tenants", column)


def _add_column(table: str, column: sa.Column) -> None:
    op.add_column(table, column)
