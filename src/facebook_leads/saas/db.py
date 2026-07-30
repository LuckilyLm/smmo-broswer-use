from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


metadata = MetaData()
JsonType = JSON().with_variant(JSONB, "postgresql")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


tenants = Table(
    "tenants",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("slug", String(255), nullable=False, unique=True),
    Column("status", String(50), nullable=False, default="active"),
    Column("timezone", String(100), nullable=False, default="UTC"),
    Column("default_target_policy", String(50), nullable=False, default="discovery_only"),
    Column("default_min_confidence", Float, nullable=False, default=0.9),
    Column("default_daily_limit", Integer, nullable=False, default=10),
    Column("default_whatsapp", String(255)),
    Column("default_email", String(255)),
    Column("default_website", String(500)),
    Column("default_contact_text", Text),
    Column("tenant_reply_enabled", Boolean, nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

users = Table(
    "users",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("display_name", String(255), nullable=False),
    Column("status", String(50), nullable=False, default="active"),
    Column("must_change_password", Boolean, nullable=False, default=False),
    Column("is_system_admin", Boolean, nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

tenant_users = Table(
    "tenant_users",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("user_id", String(64), nullable=False),
    Column("role", String(50), nullable=False, default="member"),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    UniqueConstraint("tenant_id", "user_id", name="uq_tenant_users_tenant_user"),
)

platform_accounts = Table(
    "platform_accounts",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("platform", String(50), nullable=False),
    Column("display_name", String(255), nullable=False),
    Column("external_account_id", String(255)),
    Column("external_account_name", String(255)),
    Column("connection_status", String(50), nullable=False, default="not_connected"),
    Column("config_json", JsonType, nullable=False, default=dict),
    Column("secret_ref", String(255)),
    Column("browser_runtime_id", String(64)),
    Column("login_status", String(50), nullable=False, default="unknown"),
    Column("last_login_check_at", DateTime(timezone=True)),
    Column("last_connection_error", Text),
    Column("connection_metadata", JsonType, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("last_checked_at", DateTime(timezone=True)),
    UniqueConstraint("tenant_id", "platform", "external_account_id", name="uq_platform_accounts_tenant_platform_external"),
)

browser_runtimes = Table(
    "browser_runtimes",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("platform_account_id", String(64), nullable=False),
    Column("runtime_type", String(50), nullable=False, default="browser_use_chromium_cdp"),
    Column("status", String(50), nullable=False, default="stopped"),
    Column("profile_path", Text, nullable=False),
    Column("cdp_port", Integer, nullable=False),
    Column("cdp_url", String(255), nullable=False),
    Column("browser_pid", Integer),
    Column("started_at", DateTime(timezone=True)),
    Column("last_health_check_at", DateTime(timezone=True)),
    Column("stopped_at", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    UniqueConstraint("platform_account_id", name="uq_browser_runtimes_platform_account"),
    UniqueConstraint("cdp_port", name="uq_browser_runtimes_cdp_port"),
)

campaigns = Table(
    "campaigns",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("name", String(255), nullable=False),
    Column("description", Text),
    Column("platform_account_id", String(64), nullable=False),
    Column("status", String(50), nullable=False, default="draft"),
    Column("target_policy", String(50), nullable=False, default="discovery_only"),
    Column("max_contents", Integer, nullable=False, default=5),
    Column("max_comments", Integer, nullable=False, default=80),
    Column("min_confidence", Float, nullable=False, default=0.9),
    Column("max_leads", Integer, nullable=False, default=5),
    Column("daily_limit", Integer, nullable=False, default=10),
    Column("llm_enabled", Boolean, nullable=False, default=False),
    Column("lead_detection_mode", String(50), nullable=False, default="rules_only"),
    Column("reply_mode", String(50), nullable=False, default="manual_approval"),
    Column("default_reply_template_id", String(64)),
    Column("positive_keywords_json", JsonType, nullable=False, default=list),
    Column("negative_keywords_json", JsonType, nullable=False, default=list),
    Column("excluded_authors_json", JsonType, nullable=False, default=list),
    Column("excluded_comment_patterns_json", JsonType, nullable=False, default=list),
    Column("default_whatsapp", String(255)),
    Column("default_email", String(255)),
    Column("default_website", String(500)),
    Column("default_contact_text", Text),
    Column("reply_daily_limit", Integer, nullable=False, default=30),
    Column("reply_per_minute_limit", Integer, nullable=False, default=1),
    Column("reply_per_hour_limit", Integer, nullable=False, default=10),
    Column("reply_min_interval_seconds", Integer, nullable=False, default=60),
    Column("target_regions_json", JsonType, nullable=False, default=list),
    Column("content_types_json", JsonType, nullable=False, default=list),
    Column("content_language", String(20), nullable=False, default="any"),
    Column("deleted_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

campaign_schedules = Table(
    "campaign_schedules",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("campaign_id", String(64), nullable=False),
    Column("enabled", Boolean, nullable=False, default=False),
    Column("schedule_type", String(50), nullable=False, default="manual"),
    Column("interval_minutes", Integer),
    Column("daily_time", String(5)),
    Column("cron_expression", String(255)),
    Column("timezone", String(100), nullable=False, default="UTC"),
    Column("next_run_at", DateTime(timezone=True)),
    Column("last_run_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    UniqueConstraint("tenant_id", "campaign_id", name="uq_campaign_schedules_tenant_campaign"),
)

campaign_keywords = Table(
    "campaign_keywords",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("campaign_id", String(64), nullable=False),
    Column("keyword", String(255), nullable=False),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("priority", Integer, nullable=False, default=100),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    UniqueConstraint("campaign_id", "keyword", name="uq_campaign_keywords_campaign_keyword"),
)

reply_rules = Table(
    "reply_rules",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("campaign_id", String(64), nullable=False),
    Column("name", String(255), nullable=False),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("intent_type", String(100)),
    Column("min_confidence", Float, nullable=False, default=0.9),
    Column("reply_template", Text, nullable=False),
    Column("language", String(20), nullable=False, default="en"),
    Column("approval_mode", String(50), nullable=False, default="manual"),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

reply_templates = Table(
    "reply_templates",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("name", String(255), nullable=False),
    Column("description", Text),
    Column("content", Text, nullable=False),
    Column("platform", String(50), nullable=False, default="facebook"),
    Column("language", String(20), nullable=False, default="zh-CN"),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("priority", Integer, nullable=False, default=100),
    Column("is_default", Boolean, nullable=False, default=False),
    Column("created_by", String(64)),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("archived_at", DateTime(timezone=True)),
)

reply_match_rules = Table(
    "reply_match_rules",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("campaign_id", String(64)),
    Column("reply_template_id", String(64)),
    Column("name", String(255), nullable=False),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("priority", Integer, nullable=False, default=100),
    Column("contains_any_json", JsonType, nullable=False, default=list),
    Column("contains_all_json", JsonType, nullable=False, default=list),
    Column("exact_text", Text),
    Column("regex_pattern", Text),
    Column("author_exclude_json", JsonType, nullable=False, default=list),
    Column("comment_language", String(20)),
    Column("minimum_length", Integer),
    Column("maximum_length", Integer),
    Column("created_by", String(64)),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("archived_at", DateTime(timezone=True)),
)

reply_plans = Table(
    "reply_plans",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("campaign_id", String(64), nullable=False),
    Column("execution_id", String(64)),
    Column("platform_account_id", String(64), nullable=False),
    Column("status", String(50), nullable=False, default="pending_approval"),
    Column("reply_mode", String(50), nullable=False, default="manual_approval"),
    Column("total_candidates", Integer, nullable=False, default=0),
    Column("approved_count", Integer, nullable=False, default=0),
    Column("sent_count", Integer, nullable=False, default=0),
    Column("failed_count", Integer, nullable=False, default=0),
    Column("blocked_reason", String(255)),
    Column("created_by", String(64)),
    Column("approved_by", String(64)),
    Column("approved_at", DateTime(timezone=True)),
    Column("executed_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

reply_candidates = Table(
    "reply_candidates",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("campaign_id", String(64), nullable=False),
    Column("execution_id", String(64)),
    Column("reply_plan_id", String(64)),
    Column("platform_account_id", String(64), nullable=False),
    Column("platform", String(50), nullable=False, default="facebook"),
    Column("comment_id", String(255)),
    Column("comment_fingerprint", String(255), nullable=False),
    Column("author_name", String(255)),
    Column("comment_text", Text),
    Column("source_content_url", Text),
    Column("direct_comment_url", Text),
    Column("matched_rule_id", String(64)),
    Column("matched_rule_name", String(255)),
    Column("reply_template_id", String(64)),
    Column("rendered_reply_text", Text),
    Column("status", String(50), nullable=False, default="pending_approval"),
    Column("blocked_reason", String(255)),
    Column("idempotency_key", String(64), nullable=False),
    Column("approved_by", String(64)),
    Column("approved_at", DateTime(timezone=True)),
    Column("rejected_by", String(64)),
    Column("rejected_at", DateTime(timezone=True)),
    Column("sent_at", DateTime(timezone=True)),
    Column("last_error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    UniqueConstraint("tenant_id", "campaign_id", "idempotency_key", name="uq_reply_candidates_tenant_campaign_key"),
)

reply_records = Table(
    "reply_records",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("reply_candidate_id", String(64)),
    Column("reply_plan_id", String(64)),
    Column("campaign_id", String(64), nullable=False),
    Column("platform_account_id", String(64), nullable=False),
    Column("comment_id", String(255)),
    Column("reply_text", Text, nullable=False),
    Column("status", String(50), nullable=False),
    Column("verified", Boolean, nullable=False, default=False),
    Column("error_type", String(255)),
    Column("error_message", Text),
    Column("idempotency_key", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    UniqueConstraint("tenant_id", "idempotency_key", name="uq_reply_records_tenant_key"),
)

leads = Table(
    "leads",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("campaign_id", String(64), nullable=False),
    Column("platform_account_id", String(64), nullable=False),
    Column("platform", String(50), nullable=False),
    Column("external_lead_id", String(255)),
    Column("comment_id", String(255)),
    Column("comment_fingerprint", String(255), nullable=False),
    Column("author_name", String(255)),
    Column("author_url", Text),
    Column("comment_text", Text),
    Column("source_content_url", Text),
    Column("direct_comment_url", Text),
    Column("rule_intent_level", String(50)),
    Column("final_intent_level", String(50)),
    Column("llm_confidence", Float),
    Column("llm_intent_level", String(50)),
    Column("llm_intent_types", JsonType, nullable=False, default=list),
    Column("llm_reason", Text),
    Column("suggested_reply", Text),
    Column("ownership_status", String(50)),
    Column("reply_allowed", Boolean, nullable=True),
    Column("status", String(50), nullable=False, default="new"),
    Column("manual_intent_level", String(50)),
    Column("assigned_user_id", String(64)),
    Column("contacted_at", DateTime(timezone=True)),
    Column("invalid_reason", Text),
    Column("updated_by", String(64)),
    Column("matched_search_keywords", JsonType, nullable=False, default=list),
    Column("first_discovered_at", DateTime(timezone=True)),
    Column("last_discovered_at", DateTime(timezone=True)),
    Column("discovered_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    UniqueConstraint("tenant_id", "campaign_id", "comment_fingerprint", name="uq_leads_tenant_campaign_fingerprint"),
)

lead_notes = Table(
    "lead_notes",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("lead_id", String(64), nullable=False),
    Column("author_user_id", String(64), nullable=False),
    Column("note", Text, nullable=False),
    Column("metadata_json", JsonType, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

executions = Table(
    "executions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("campaign_id", String(64), nullable=False),
    Column("run_id", String(255)),
    Column("platform", String(50), nullable=False),
    Column("status", String(50), nullable=False),
    Column("trigger_type", String(50), nullable=False, default="manual"),
    Column("stage", String(100)),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("elapsed_ms", Integer),
    Column("total_keywords", Integer, nullable=False, default=0),
    Column("completed_keywords", Integer, nullable=False, default=0),
    Column("failed_keywords", Integer, nullable=False, default=0),
    Column("current_keyword", String(255)),
    Column("progress_percent", Integer, nullable=False, default=0),
    Column("cancel_requested", Boolean, nullable=False, default=False),
    Column("cancel_requested_at", DateTime(timezone=True)),
    Column("config_snapshot", JsonType, nullable=False, default=dict),
    Column("scanned_contents", Integer, nullable=False, default=0),
    Column("scanned_comments", Integer, nullable=False, default=0),
    Column("lead_candidates", Integer, nullable=False, default=0),
    Column("eligible_count", Integer, nullable=False, default=0),
    Column("selected_count", Integer, nullable=False, default=0),
    Column("prompt_tokens", Integer, nullable=False, default=0),
    Column("completion_tokens", Integer, nullable=False, default=0),
    Column("total_tokens", Integer, nullable=False, default=0),
    Column("send_disabled", Boolean, nullable=False, default=True),
    Column("error_type", String(255)),
    Column("error_message", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

execution_queue_items = Table(
    "execution_queue_items",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("campaign_id", String(64), nullable=False),
    Column("execution_id", String(64), nullable=False),
    Column("status", String(50), nullable=False, default="queued"),
    Column("priority", Integer, nullable=False, default=100),
    Column("schedule_trigger_key", String(255)),
    Column("attempt_token", String(64)),
    Column("claimed_by", String(255)),
    Column("queued_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("run_after", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("attempt_count", Integer, nullable=False, default=0),
    Column("max_attempts", Integer, nullable=False, default=3),
    Column("error_type", String(255)),
    Column("error_message", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    UniqueConstraint("tenant_id", "schedule_trigger_key", name="uq_execution_queue_schedule_trigger"),
)

execution_keywords = Table(
    "execution_keywords",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("execution_id", String(64), nullable=False),
    Column("campaign_keyword_id", String(64)),
    Column("keyword", String(255), nullable=False),
    Column("attempt_number", Integer, nullable=False, default=1),
    Column("status", String(50), nullable=False, default="queued"),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("elapsed_ms", Integer, nullable=False, default=0),
    Column("discovered_contents", Integer, nullable=False, default=0),
    Column("scanned_comments", Integer, nullable=False, default=0),
    Column("lead_candidates", Integer, nullable=False, default=0),
    Column("eligible_count", Integer, nullable=False, default=0),
    Column("selected_count", Integer, nullable=False, default=0),
    Column("prompt_tokens", Integer, nullable=False, default=0),
    Column("completion_tokens", Integer, nullable=False, default=0),
    Column("total_tokens", Integer, nullable=False, default=0),
    Column("error_type", String(255)),
    Column("error_message", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    UniqueConstraint("execution_id", "keyword", name="uq_execution_keywords_execution_keyword"),
)

token_usage = Table(
    "token_usage",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("campaign_id", String(64)),
    Column("execution_id", String(64)),
    Column("execution_keyword_id", String(64)),
    Column("provider", String(50), nullable=False),
    Column("model", String(255)),
    Column("prompt_tokens", Integer),
    Column("completion_tokens", Integer),
    Column("total_tokens", Integer),
    Column("request_count", Integer),
    Column("estimated_cost", Float),
    Column("elapsed_ms", Integer),
    Column("attempt_number", Integer, nullable=False, default=1),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

worker_heartbeats = Table(
    "worker_heartbeats",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("worker_id", String(255), nullable=False, unique=True),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("status", String(50), nullable=False, default="online"),
    Column("current_queue_item_id", String(64)),
    Column("last_error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", String(128), primary_key=True),
    Column("user_id", String(64), nullable=False),
    Column("tenant_id", String(64), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("last_seen_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

plans = Table(
    "plans",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("code", String(50), nullable=False, unique=True),
    Column("name", String(255), nullable=False),
    Column("description", Text),
    Column("status", String(50), nullable=False, default="active"),
    Column("max_users", Integer),
    Column("max_platform_accounts", Integer),
    Column("max_campaigns", Integer),
    Column("max_monthly_executions", Integer),
    Column("max_monthly_tokens", Integer),
    Column("max_monthly_leads", Integer),
    Column("allow_scheduler", Boolean, nullable=False, default=False),
    Column("allow_multi_keyword", Boolean, nullable=False, default=False),
    Column("allow_advanced_reports", Boolean, nullable=False, default=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

tenant_subscriptions = Table(
    "tenant_subscriptions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("plan_id", String(64), nullable=False),
    Column("status", String(50), nullable=False, default="active"),
    Column("started_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("trial_ends_at", DateTime(timezone=True)),
    Column("current_period_start", DateTime(timezone=True)),
    Column("current_period_end", DateTime(timezone=True)),
    Column("overrides_json", JsonType, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    UniqueConstraint("tenant_id", name="uq_tenant_subscriptions_tenant"),
)

tenant_invitations = Table(
    "tenant_invitations",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("email", String(255), nullable=False),
    Column("role", String(50), nullable=False, default="member"),
    Column("token_hash", String(64), nullable=False, unique=True),
    Column("status", String(50), nullable=False, default="pending"),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("invited_by_user_id", String(64)),
    Column("accepted_by_user_id", String(64)),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

audit_logs = Table(
    "audit_logs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64)),
    Column("user_id", String(64)),
    Column("action", String(100), nullable=False),
    Column("resource_type", String(100), nullable=False),
    Column("resource_id", String(64)),
    Column("ip_address", String(64)),
    Column("user_agent", Text),
    Column("metadata_json", JsonType, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

notifications = Table(
    "notifications",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False),
    Column("user_id", String(64)),
    Column("type", String(100), nullable=False),
    Column("severity", String(50), nullable=False, default="info"),
    Column("title", String(255), nullable=False),
    Column("message", Text, nullable=False),
    Column("resource_type", String(100)),
    Column("resource_id", String(64)),
    Column("dedupe_key", String(255)),
    Column("read_at", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    UniqueConstraint("tenant_id", "dedupe_key", name="uq_notifications_tenant_dedupe"),
)

Index("ix_leads_tenant_created_at", leads.c.tenant_id, leads.c.created_at)
Index("ix_leads_tenant_status", leads.c.tenant_id, leads.c.status)
Index("ix_leads_tenant_campaign", leads.c.tenant_id, leads.c.campaign_id)
Index("ix_leads_comment_fingerprint", leads.c.comment_fingerprint)
Index("ix_leads_tenant_assigned", leads.c.tenant_id, leads.c.assigned_user_id)
Index("ix_leads_tenant_intent", leads.c.tenant_id, leads.c.final_intent_level, leads.c.manual_intent_level)
Index("ix_lead_notes_tenant_lead", lead_notes.c.tenant_id, lead_notes.c.lead_id)
Index("ix_executions_tenant_started_at", executions.c.tenant_id, executions.c.started_at)
Index("ix_executions_tenant_campaign", executions.c.tenant_id, executions.c.campaign_id)
Index("ix_token_usage_tenant_created_at", token_usage.c.tenant_id, token_usage.c.created_at)
Index("ix_token_usage_tenant_campaign", token_usage.c.tenant_id, token_usage.c.campaign_id)
Index("ix_campaigns_tenant_status", campaigns.c.tenant_id, campaigns.c.status)
Index("ix_campaign_schedules_due", campaign_schedules.c.enabled, campaign_schedules.c.next_run_at)
Index("ix_browser_runtimes_tenant_account", browser_runtimes.c.tenant_id, browser_runtimes.c.platform_account_id)
Index("ix_browser_runtimes_tenant_status", browser_runtimes.c.tenant_id, browser_runtimes.c.status)
Index("ix_queue_status_run_after", execution_queue_items.c.status, execution_queue_items.c.run_after, execution_queue_items.c.priority)
Index("ix_execution_keywords_execution", execution_keywords.c.execution_id)
Index("ix_subscriptions_tenant_status", tenant_subscriptions.c.tenant_id, tenant_subscriptions.c.status)
Index("ix_invitations_tenant_status", tenant_invitations.c.tenant_id, tenant_invitations.c.status)
Index("ix_audit_tenant_created", audit_logs.c.tenant_id, audit_logs.c.created_at)
Index("ix_audit_tenant_action", audit_logs.c.tenant_id, audit_logs.c.action)
Index("ix_notifications_tenant_created", notifications.c.tenant_id, notifications.c.created_at)
Index("ix_notifications_tenant_read", notifications.c.tenant_id, notifications.c.read_at)
Index("ix_reply_templates_tenant", reply_templates.c.tenant_id, reply_templates.c.enabled)
Index("ix_reply_match_rules_tenant_campaign", reply_match_rules.c.tenant_id, reply_match_rules.c.campaign_id)
Index("ix_reply_candidates_tenant_status", reply_candidates.c.tenant_id, reply_candidates.c.status)
Index("ix_reply_plans_tenant_status", reply_plans.c.tenant_id, reply_plans.c.status)
Index("ix_reply_records_tenant_created", reply_records.c.tenant_id, reply_records.c.created_at)
Index(
    "uq_token_usage_execution_keyword",
    token_usage.c.execution_keyword_id,
    unique=True,
    postgresql_where=token_usage.c.execution_keyword_id.is_not(None),
    sqlite_where=token_usage.c.execution_keyword_id.is_not(None),
)

TABLES = {
    table.name: table
    for table in [
        tenants,
        users,
        tenant_users,
        platform_accounts,
        browser_runtimes,
        campaigns,
        campaign_schedules,
        campaign_keywords,
        reply_rules,
        reply_templates,
        reply_match_rules,
        reply_plans,
        reply_candidates,
        reply_records,
        leads,
        lead_notes,
        executions,
        execution_queue_items,
        execution_keywords,
        token_usage,
        worker_heartbeats,
        sessions,
        plans,
        tenant_subscriptions,
        tenant_invitations,
        audit_logs,
        notifications,
    ]
}


def resolve_database_url(database_url: str | None = None, *, sqlite_path: str | Path | None = None) -> str:
    if database_url:
        return _path_to_sqlite_url(database_url) if _looks_like_path(database_url) else database_url
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    if sqlite_path is not None:
        return _path_to_sqlite_url(sqlite_path)
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        raise RuntimeError("DATABASE_URL or POSTGRES_PASSWORD is required for the SaaS database")
    user = os.getenv("POSTGRES_USER", "saas_user")
    db = os.getenv("POSTGRES_DB", "facebook_leads_saas")
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


def create_saas_engine(database_url: str) -> Engine:
    kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}
    if not database_url.startswith("sqlite"):
        kwargs.update(
            {
                "pool_size": int(os.getenv("SAAS_DB_POOL_SIZE", "10")),
                "max_overflow": int(os.getenv("SAAS_DB_MAX_OVERFLOW", "20")),
                "pool_recycle": int(os.getenv("SAAS_DB_POOL_RECYCLE", "1800")),
            }
        )
    return create_engine(database_url, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def transaction(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory.begin() as session:
        yield session


def _looks_like_path(value: str) -> bool:
    return "://" not in value and "+" not in value


def _path_to_sqlite_url(value: str | Path) -> str:
    path = Path(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.as_posix()}"
