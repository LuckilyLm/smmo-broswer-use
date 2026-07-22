"""scheduler queue

Revision ID: 003_scheduler_queue
Revises: 002_browser_runtime
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_scheduler_queue"
down_revision = "002_browser_runtime"
branch_labels = None
depends_on = None


def json_type():
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "campaign_schedules",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(64), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("schedule_type", sa.String(50), nullable=False),
        sa.Column("interval_minutes", sa.Integer()),
        sa.Column("daily_time", sa.String(5)),
        sa.Column("cron_expression", sa.String(255)),
        sa.Column("timezone", sa.String(100), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "campaign_id", name="uq_campaign_schedules_tenant_campaign"),
    )
    op.add_column("leads", sa.Column("matched_search_keywords", json_type(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("leads", sa.Column("first_discovered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("executions", sa.Column("trigger_type", sa.String(50), nullable=False, server_default="manual"))
    op.add_column("executions", sa.Column("total_keywords", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("executions", sa.Column("completed_keywords", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("executions", sa.Column("failed_keywords", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("executions", sa.Column("current_keyword", sa.String(255), nullable=True))
    op.add_column("executions", sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("executions", sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("executions", sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("executions", sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("executions", sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "execution_queue_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(64), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("execution_id", sa.String(64), sa.ForeignKey("executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("schedule_trigger_key", sa.String(255)),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(255)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "schedule_trigger_key", name="uq_execution_queue_schedule_trigger"),
    )
    op.create_table(
        "execution_keywords",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("execution_id", sa.String(64), sa.ForeignKey("executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_keyword_id", sa.String(64), sa.ForeignKey("campaign_keywords.id", ondelete="SET NULL")),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("discovered_contents", sa.Integer(), nullable=False),
        sa.Column("scanned_comments", sa.Integer(), nullable=False),
        sa.Column("lead_candidates", sa.Integer(), nullable=False),
        sa.Column("eligible_count", sa.Integer(), nullable=False),
        sa.Column("selected_count", sa.Integer(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("error_type", sa.String(255)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("token_usage", sa.Column("execution_keyword_id", sa.String(64)))
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key("fk_token_usage_execution_keyword", "token_usage", "execution_keywords", ["execution_keyword_id"], ["id"], ondelete="SET NULL")
    op.create_table(
        "worker_heartbeats",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("worker_id", sa.String(255), nullable=False, unique=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("current_queue_item_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campaign_schedules_due", "campaign_schedules", ["enabled", "next_run_at"])
    op.create_index("ix_queue_status_run_after", "execution_queue_items", ["status", "run_after", "priority"])
    op.create_index("ix_execution_keywords_execution", "execution_keywords", ["execution_id"])


def downgrade() -> None:
    op.drop_index("ix_execution_keywords_execution", table_name="execution_keywords")
    op.drop_index("ix_queue_status_run_after", table_name="execution_queue_items")
    op.drop_index("ix_campaign_schedules_due", table_name="campaign_schedules")
    op.drop_table("worker_heartbeats")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_token_usage_execution_keyword", "token_usage", type_="foreignkey")
    op.drop_column("token_usage", "execution_keyword_id")
    op.drop_table("execution_keywords")
    op.drop_table("execution_queue_items")
    for column in ["total_tokens", "completion_tokens", "prompt_tokens", "cancel_requested", "progress_percent", "current_keyword", "failed_keywords", "completed_keywords", "total_keywords", "trigger_type"]:
        op.drop_column("executions", column)
    for column in ["last_discovered_at", "first_discovered_at", "matched_search_keywords"]:
        op.drop_column("leads", column)
    op.drop_table("campaign_schedules")
