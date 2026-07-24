from __future__ import annotations

import secrets
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .auth import hash_password, needs_rehash, verify_password
from .artifacts import safe_artifact_path
from .config import ProductionConfig
from .db import utc_now
from .models import PLATFORMS, TARGET_POLICIES, TenantContext
from .persist import persist_orchestrator_result
from .providers import BasePlatformProvider, PlatformRunContext, ProviderRunRequest, default_provider_registry
from .reply_automation import build_candidate_key, comments_from_scan_artifacts, match_comment, render_template
from .productization import (
    AuditService,
    NotificationService,
    QuotaService,
    SystemAdminService,
    TenantAdminService,
    bootstrap_system_admin,
    natural_month_period,
    seed_plans,
)
from .rbac import Permission, require_permission
from .runtime import BrowserRuntimeError, BrowserRuntimeRegistry, safe_runtime
from .services import AuthService, CampaignService, ExecutionService, RuntimeService
from .storage import SaaSStorage


PLATFORM_ACCOUNT_WRITE_FIELDS = {"platform", "display_name", "external_account_id", "external_account_name"}
CAMPAIGN_WRITE_FIELDS = {
    "name",
    "platform_account_id",
    "status",
    "target_policy",
    "max_contents",
    "max_comments",
    "min_confidence",
    "max_leads",
    "daily_limit",
    "llm_enabled",
    "lead_detection_mode",
    "reply_mode",
    "default_reply_template_id",
    "positive_keywords_json",
    "negative_keywords_json",
    "excluded_authors_json",
    "excluded_comment_patterns_json",
    "default_whatsapp",
    "default_email",
    "default_website",
    "default_contact_text",
    "reply_daily_limit",
    "reply_per_minute_limit",
    "reply_per_hour_limit",
    "reply_min_interval_seconds",
}
KEYWORD_WRITE_FIELDS = {"keyword", "enabled", "priority"}
REPLY_RULE_WRITE_FIELDS = {"campaign_id", "name", "enabled", "intent_type", "min_confidence", "reply_template", "language", "approval_mode"}
REPLY_TEMPLATE_WRITE_FIELDS = {"name", "description", "content", "platform", "language", "enabled", "priority", "is_default"}
REPLY_MATCH_RULE_WRITE_FIELDS = {
    "campaign_id",
    "reply_template_id",
    "name",
    "enabled",
    "priority",
    "contains_any_json",
    "contains_all_json",
    "exact_text",
    "regex_pattern",
    "author_exclude_json",
    "comment_language",
    "minimum_length",
    "maximum_length",
}
REPLY_MODES = {"disabled", "manual_approval", "automatic"}
LEAD_DETECTION_MODES = {"rules_only", "rules_with_llm"}


class SaaSService:
    _runtime_locks: set[str] = set()

    def __init__(
        self,
        storage: SaaSStorage,
        *,
        providers: dict[str, BasePlatformProvider] | None = None,
        artifacts_root: str | Path = "artifacts/saas",
        runtime_registry: BrowserRuntimeRegistry | None = None,
        max_queued_executions_per_tenant: int | None = None,
        session_ttl_hours: int | None = None,
        session_idle_timeout_hours: int | None = None,
        config: ProductionConfig | None = None,
    ) -> None:
        self.storage = storage
        self.providers = providers or default_provider_registry()
        self.artifacts_root = Path(artifacts_root)
        self.runtime_registry = runtime_registry or BrowserRuntimeRegistry(storage)
        self.config = config
        self.max_queued_executions_per_tenant = max_queued_executions_per_tenant or 50
        self.session_ttl = timedelta(hours=session_ttl_hours or 168)
        self.session_idle_timeout = timedelta(hours=session_idle_timeout_hours or 24)
        self.session_touch_interval = timedelta(minutes=5)
        self.auth = AuthService(self)
        self.runtimes = RuntimeService(config)
        self.campaigns = CampaignService()
        self.executions = ExecutionService()
        self.notifications = NotificationService(storage)
        self.audit = AuditService(storage)
        self.quota = QuotaService(storage, self.notifications)
        self.tenant_admin = TenantAdminService(self)
        self.system_admin = SystemAdminService(self)

    def create_tenant(self, name: str, slug: str, **settings: Any) -> dict[str, Any]:
        allowed_settings = {
            "timezone",
            "default_target_policy",
            "default_min_confidence",
            "default_daily_limit",
            "default_whatsapp",
            "default_email",
            "default_website",
            "default_contact_text",
            "tenant_reply_enabled",
        }
        tenant = self.storage.insert("tenants", {"name": name, "slug": slug, "status": settings.get("status", "active"), **{k: v for k, v in settings.items() if k in allowed_settings}})
        plans = seed_plans(self.storage)
        start, end = natural_month_period()
        self.storage.insert("tenant_subscriptions", {"tenant_id": tenant["id"], "plan_id": plans[settings.get("plan_code", "legacy")]["id"], "status": "active", "started_at": utc_now(), "current_period_start": start, "current_period_end": end, "overrides_json": {}})
        return tenant

    def create_user(self, email: str, password: str, display_name: str, *, status: str = "active", must_change_password: bool = False, is_system_admin: bool = False) -> dict[str, Any]:
        return self.storage.insert("users", {"email": email.lower(), "password_hash": hash_password(password), "display_name": display_name, "status": status, "must_change_password": must_change_password, "is_system_admin": is_system_admin})

    def bootstrap_admin(self, email: str | None, password: str | None) -> dict[str, Any] | None:
        if not email or not password or self.storage.count("users"):
            return None
        tenant = self.create_tenant("Default", "default")
        user = self.create_user(email, password, "Administrator", must_change_password=True)
        self.add_user_to_tenant(tenant["id"], user["id"], role="admin")
        return user

    def bootstrap_system_admin(self, email: str | None) -> bool:
        return bootstrap_system_admin(self.storage, email)

    def add_user_to_tenant(self, tenant_id: str, user_id: str, *, role: str = "member") -> dict[str, Any]:
        return self.storage.insert("tenant_users", {"tenant_id": tenant_id, "user_id": user_id, "role": role})

    def login(self, email: str, password: str) -> dict[str, Any]:
        user = self.storage.find_one("users", {"email": email.lower(), "status": "active"})
        if not user or not verify_password(password, user["password_hash"]):
            self.audit.record(action="auth.login_failed", resource_type="user", user_id=user["id"] if user else None, metadata={"email": email})
            raise PermissionError("invalid credentials")
        if needs_rehash(user["password_hash"]):
            user = self.storage.update_by_id(
                "users",
                user["id"],
                {"password_hash": hash_password(password)},
            ) or user
        membership = self.storage.find_one("tenant_users", {"user_id": user["id"]}, order_by=["created_at"])
        if not membership:
            raise PermissionError("user has no tenant")
        token = f"sess_{secrets.token_urlsafe(24)}"
        now = utc_now()
        self.storage.insert(
            "sessions",
            {
                "id": token,
                "user_id": user["id"],
                "tenant_id": membership["tenant_id"],
                "expires_at": now + self.session_ttl,
                "last_seen_at": now,
                "revoked_at": None,
            },
        )
        self.audit.record(action="auth.login_success", resource_type="session", tenant_id=membership["tenant_id"], user_id=user["id"])
        return {"access_token": token, "user": _public_user(user), "tenant_id": membership["tenant_id"]}

    def logout(self, token: str) -> None:
        session = self.storage.get_by_id("sessions", token)
        self.storage.delete_by_id("sessions", token)
        if session:
            self.audit.record(action="auth.logout", resource_type="session", tenant_id=session["tenant_id"], user_id=session["user_id"])

    def context_from_token(self, token: str) -> TenantContext:
        session = self.storage.get_by_id("sessions", token)
        if not session:
            raise PermissionError("invalid session")
        now = utc_now()
        expires_at = _as_datetime(session.get("expires_at"))
        last_seen_at = _as_datetime(session.get("last_seen_at"))
        if session.get("revoked_at") or not expires_at or expires_at <= now:
            raise PermissionError("invalid session")
        if not last_seen_at or last_seen_at <= now - self.session_idle_timeout:
            raise PermissionError("invalid session")
        user = self.storage.get_by_id("users", session["user_id"])
        tenant = self.storage.get_by_id("tenants", session["tenant_id"])
        if not user or user.get("status") != "active" or not tenant or tenant.get("status") not in {"active", "suspended"}:
            raise PermissionError("invalid session")
        membership = self.storage.find_one("tenant_users", {"tenant_id": session["tenant_id"], "user_id": session["user_id"]})
        if not membership:
            raise PermissionError("invalid session")
        if last_seen_at <= now - self.session_touch_interval:
            self.storage.update_by_id("sessions", token, {"last_seen_at": now})
        return TenantContext(tenant_id=session["tenant_id"], user_id=session["user_id"], role=membership["role"])

    def revoke_user_sessions(self, user_id: str) -> int:
        sessions = self.storage.list("sessions", filters={"user_id": user_id}, limit=10000)
        now = utc_now()
        for session in sessions:
            if not session.get("revoked_at"):
                self.storage.update_by_id("sessions", session["id"], {"revoked_at": now})
        return len(sessions)

    def change_password(self, context: TenantContext, current_password: str, new_password: str) -> None:
        user = self.storage.get_by_id("users", context.user_id)
        if not user or not verify_password(current_password, user["password_hash"]):
            raise PermissionError("current password is incorrect")
        if len(new_password) < 8:
            raise ValueError("new password must be at least 8 characters")
        self.storage.update_by_id(
            "users",
            context.user_id,
            {"password_hash": hash_password(new_password), "must_change_password": False},
        )
        self.revoke_user_sessions(context.user_id)
        self.audit.record(action="auth.password_change", resource_type="user", resource_id=context.user_id, tenant_id=context.tenant_id, user_id=context.user_id)

    def me(self, context: TenantContext) -> dict[str, Any]:
        user = self.storage.get_by_id("users", context.user_id)
        tenant = self.storage.get_by_id("tenants", context.tenant_id)
        return {"user": _public_user(user or {}), "tenant": tenant, "role": context.role}

    def tenants(self, context: TenantContext) -> list[dict[str, Any]]:
        memberships = self.storage.list("tenant_users", filters={"user_id": context.user_id}, limit=100)
        tenants = [self.storage.get_by_id("tenants", row["tenant_id"]) for row in memberships]
        return sorted([tenant for tenant in tenants if tenant], key=lambda row: row["name"])

    def switch_tenant(self, context: TenantContext, tenant_id: str) -> TenantContext:
        membership = self.storage.find_one("tenant_users", {"tenant_id": tenant_id, "user_id": context.user_id})
        if not membership:
            raise PermissionError("tenant access denied")
        return TenantContext(tenant_id=tenant_id, user_id=context.user_id, role=membership["role"])

    def rotate_session(self, token: str, tenant_id: str) -> dict[str, Any]:
        return self.auth.rotate_session(token, tenant_id)

    def list_platform_accounts(self, context: TenantContext) -> list[dict[str, Any]]:
        accounts = self.storage.list("platform_accounts", tenant_id=context.tenant_id)
        for account in accounts:
            runtime = self.runtime_registry.get_runtime(context, account["id"])
            account["runtime"] = safe_runtime(runtime) if runtime else None
        return accounts

    def create_platform_account(self, context: TenantContext, data: dict[str, Any]) -> dict[str, Any]:
        self._require_tenant_writable(context)
        require_permission(context, Permission.PLATFORM_ACCOUNT_WRITE)
        self.quota.check_quota(context.tenant_id, "platform_accounts")
        payload = _pick(_without_secret_fields(data), PLATFORM_ACCOUNT_WRITE_FIELDS)
        platform = payload.get("platform")
        if platform not in PLATFORMS:
            raise ValueError("unsupported platform")
        account = self.storage.insert("platform_accounts", {**payload, "tenant_id": context.tenant_id, "config_json": {}, "connection_metadata": {}, "login_status": "unknown"})
        self.audit.record(action="platform_account.create", resource_type="platform_account", resource_id=account["id"], tenant_id=context.tenant_id, user_id=context.user_id, metadata=payload)
        return account

    def update_platform_account(self, context: TenantContext, account_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        self._require_tenant_writable(context)
        account = self.storage.get_by_id("platform_accounts", account_id, tenant_id=context.tenant_id)
        if not account:
            return None
        require_permission(context, Permission.PLATFORM_ACCOUNT_WRITE)
        payload = _pick(_without_secret_fields(data), PLATFORM_ACCOUNT_WRITE_FIELDS)
        if payload.get("platform") not in {None, *PLATFORMS}:
            raise ValueError("unsupported platform")
        return self.storage.update_by_id("platform_accounts", account_id, payload, tenant_id=context.tenant_id)

    def delete_platform_account(self, context: TenantContext, account_id: str) -> None:
        self._require_tenant_writable(context)
        self._require_platform_account(context, account_id)
        require_permission(context, Permission.PLATFORM_ACCOUNT_WRITE)
        if self.storage.find_one("campaigns", {"tenant_id": context.tenant_id, "platform_account_id": account_id, "deleted_at": None}):
            raise ServiceConflictError("platform_account_in_use")
        runtime = self.runtime_registry.get_runtime(context, account_id)
        if runtime:
            self.runtime_registry.stop_runtime(context, account_id)
        self.storage.delete_by_id("platform_accounts", account_id, tenant_id=context.tenant_id)

    def connect_platform_account(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_runtime_available()
        self._require_platform_account(context, account_id)
        require_permission(context, Permission.RUNTIME_CONTROL)
        runtime = self.runtime_registry.start_runtime(context, account_id)
        self.storage.update_by_id("platform_accounts", account_id, {"connection_status": "login_required"}, tenant_id=context.tenant_id)
        return {"runtime": safe_runtime(runtime), "connection_status": "login_required", "login_status": "unknown"}

    async def check_platform_login(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_runtime_available()
        self._require_platform_account(context, account_id)
        require_permission(context, Permission.RUNTIME_CONTROL)
        return await self.runtime_registry.check_login(context, account_id)

    def reconnect_platform_account(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_runtime_available()
        self._require_platform_account(context, account_id)
        require_permission(context, Permission.RUNTIME_CONTROL)
        runtime = self.runtime_registry.restart_runtime(context, account_id)
        self.storage.update_by_id("platform_accounts", account_id, {"connection_status": "login_required"}, tenant_id=context.tenant_id)
        return {"runtime": safe_runtime(runtime), "connection_status": "login_required"}

    def stop_platform_runtime(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_runtime_available()
        self._require_platform_account(context, account_id)
        require_permission(context, Permission.RUNTIME_CONTROL)
        runtime = self.runtime_registry.stop_runtime(context, account_id)
        return {"runtime": safe_runtime(runtime)}

    def restart_platform_runtime(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_runtime_available()
        self._require_platform_account(context, account_id)
        require_permission(context, Permission.RUNTIME_CONTROL)
        runtime = self.runtime_registry.restart_runtime(context, account_id)
        return {"runtime": safe_runtime(runtime)}

    def reset_platform_profile(self, context: TenantContext, account_id: str, *, confirm: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_runtime_available()
        self._require_platform_account(context, account_id)
        require_permission(context, Permission.RUNTIME_CONTROL)
        runtime = self.runtime_registry.reset_profile(context, account_id, confirm=confirm)
        return {"runtime": safe_runtime(runtime), "login_status": "unknown"}

    def get_platform_runtime(self, context: TenantContext, account_id: str) -> dict[str, Any] | None:
        self._require_platform_account(context, account_id)
        runtime = self.runtime_registry.get_runtime(context, account_id)
        return safe_runtime(runtime) if runtime else None

    def list_campaigns(self, context: TenantContext, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        limit = _safe_limit(limit)
        campaigns = self.storage.list("campaigns", tenant_id=context.tenant_id, filters={"deleted_at": None}, limit=limit, offset=offset)
        for campaign in campaigns:
            campaign["schedule"] = self.get_campaign_schedule(context, campaign["id"])
        return campaigns

    def create_campaign(self, context: TenantContext, data: dict[str, Any]) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self.quota.check_quota(context.tenant_id, "campaigns")
        payload = _pick(data, CAMPAIGN_WRITE_FIELDS)
        if payload.get("target_policy", "discovery_only") not in TARGET_POLICIES:
            raise ValueError("invalid target_policy")
        if payload.get("reply_mode") not in {None, *REPLY_MODES}:
            raise ValueError("invalid_reply_mode")
        if payload.get("lead_detection_mode") not in {None, *LEAD_DETECTION_MODES}:
            raise ValueError("invalid_lead_detection_mode")
        if payload.get("reply_mode") == "automatic" and context.role not in {"owner", "admin"}:
            raise PermissionError("permission denied")
        account = self.storage.get_by_id("platform_accounts", payload["platform_account_id"], tenant_id=context.tenant_id)
        if not account:
            raise PermissionError("platform account not found")
        require_permission(context, Permission.CAMPAIGN_WRITE)
        defaults = {
            "status": "draft",
            "target_policy": "discovery_only",
            "max_contents": 5,
            "max_comments": 80,
            "min_confidence": 0.9,
            "max_leads": 5,
            "daily_limit": 10,
            "llm_enabled": False,
            "lead_detection_mode": "rules_only",
            "reply_mode": "manual_approval",
            "positive_keywords_json": [],
            "negative_keywords_json": [],
            "excluded_authors_json": [],
            "excluded_comment_patterns_json": [],
            "reply_daily_limit": 30,
            "reply_per_minute_limit": 1,
            "reply_per_hour_limit": 10,
            "reply_min_interval_seconds": 60,
        }
        campaign = self.storage.insert("campaigns", {**defaults, **payload, "tenant_id": context.tenant_id})
        self.audit.record(action="campaign.create", resource_type="campaign", resource_id=campaign["id"], tenant_id=context.tenant_id, user_id=context.user_id, metadata=payload)
        return campaign

    def update_campaign(self, context: TenantContext, campaign_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        self._require_tenant_writable(context)
        if not self.storage.get_by_id("campaigns", campaign_id, tenant_id=context.tenant_id):
            return None
        require_permission(context, Permission.CAMPAIGN_WRITE)
        payload = _pick(data, CAMPAIGN_WRITE_FIELDS)
        if payload.get("target_policy") not in {None, *TARGET_POLICIES}:
            raise ValueError("invalid target_policy")
        if payload.get("reply_mode") not in {None, *REPLY_MODES}:
            raise ValueError("invalid_reply_mode")
        if payload.get("lead_detection_mode") not in {None, *LEAD_DETECTION_MODES}:
            raise ValueError("invalid_lead_detection_mode")
        if payload.get("reply_mode") == "automatic" and context.role not in {"owner", "admin"}:
            raise PermissionError("permission denied")
        if payload.get("platform_account_id") and not self.storage.get_by_id("platform_accounts", payload["platform_account_id"], tenant_id=context.tenant_id):
            raise PermissionError("platform account not found")
        return self.storage.update_by_id("campaigns", campaign_id, payload, tenant_id=context.tenant_id)

    def delete_campaign(self, context: TenantContext, campaign_id: str) -> None:
        self._require_tenant_writable(context)
        self._require_campaign(context, campaign_id)
        require_permission(context, Permission.CAMPAIGN_WRITE)
        active = self.storage.query_one(
            "SELECT id FROM executions WHERE tenant_id = ? AND campaign_id = ? AND status IN (?, ?) LIMIT 1",
            [context.tenant_id, campaign_id, "queued", "running"],
        )
        if active:
            raise ServiceConflictError("campaign_has_active_execution")
        self.storage.update_by_id(
            "campaigns",
            campaign_id,
            {"status": "archived", "deleted_at": utc_now()},
            tenant_id=context.tenant_id,
        )

    def list_keywords(self, context: TenantContext, campaign_id: str) -> list[dict[str, Any]]:
        self._require_campaign(context, campaign_id)
        return self.storage.list("campaign_keywords", tenant_id=context.tenant_id, filters={"campaign_id": campaign_id})

    def create_keyword(self, context: TenantContext, campaign_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_campaign(context, campaign_id)
        require_permission(context, Permission.KEYWORD_WRITE)
        if data.get("enabled", True) and self.storage.count("campaign_keywords", tenant_id=context.tenant_id, filters={"campaign_id": campaign_id, "enabled": True}) >= 1:
            self.quota.require_feature(context.tenant_id, "allow_multi_keyword")
        return self.storage.insert("campaign_keywords", {"enabled": True, "priority": 100, **_pick(data, KEYWORD_WRITE_FIELDS), "tenant_id": context.tenant_id, "campaign_id": campaign_id})

    def update_keyword(self, context: TenantContext, keyword_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        self._require_tenant_writable(context)
        if not self.storage.get_by_id("campaign_keywords", keyword_id, tenant_id=context.tenant_id):
            return None
        require_permission(context, Permission.KEYWORD_WRITE)
        return self.storage.update_by_id("campaign_keywords", keyword_id, _pick(data, KEYWORD_WRITE_FIELDS), tenant_id=context.tenant_id)

    def delete_keyword(self, context: TenantContext, keyword_id: str) -> None:
        self._require_tenant_writable(context)
        if not self.storage.get_by_id("campaign_keywords", keyword_id, tenant_id=context.tenant_id):
            raise PermissionError("keyword not found")
        require_permission(context, Permission.KEYWORD_WRITE)
        self.storage.delete_by_id("campaign_keywords", keyword_id, tenant_id=context.tenant_id)

    def list_leads(self, context: TenantContext, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        allowed = {"campaign_id", "platform", "status", "rule_intent_level", "final_intent_level", "reply_allowed", "keyword"}
        limit = _safe_limit(limit)
        rows = self.storage.list("leads", tenant_id=context.tenant_id, filters={k: v for k, v in (filters or {}).items() if k in allowed}, limit=limit, offset=max(offset, 0))
        total = self.storage.count("leads", tenant_id=context.tenant_id, filters={k: v for k, v in (filters or {}).items() if k in allowed})
        return {"items": rows[:limit], "limit": limit, "offset": max(offset, 0), "total": total}

    def get_lead(self, context: TenantContext, lead_id: str) -> dict[str, Any] | None:
        return self.storage.get_by_id("leads", lead_id, tenant_id=context.tenant_id)

    def list_reply_templates(self, context: TenantContext, *, include_archived: bool = False) -> list[dict[str, Any]]:
        filters = {} if include_archived else {"archived_at": None}
        return self.storage.list("reply_templates", tenant_id=context.tenant_id, filters=filters, limit=200, order_by=["priority", "created_at"])

    def create_reply_template(self, context: TenantContext, data: dict[str, Any]) -> dict[str, Any]:
        self._require_tenant_writable(context)
        require_permission(context, Permission.REPLY_RULE_WRITE)
        payload = {"enabled": True, "priority": 100, "is_default": False, "platform": "facebook", "language": "zh-CN", **_pick(data, REPLY_TEMPLATE_WRITE_FIELDS)}
        render_template(str(payload.get("content") or ""), _preview_template_values())
        row = self.storage.insert("reply_templates", {**payload, "tenant_id": context.tenant_id, "created_by": context.user_id})
        if row.get("is_default"):
            self._clear_other_default_templates(context, row["id"])
        self.audit.record(action="reply_template.create", resource_type="reply_template", resource_id=row["id"], tenant_id=context.tenant_id, user_id=context.user_id)
        return row

    def update_reply_template(self, context: TenantContext, template_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        self._require_tenant_writable(context)
        if not self.storage.get_by_id("reply_templates", template_id, tenant_id=context.tenant_id):
            return None
        require_permission(context, Permission.REPLY_RULE_WRITE)
        payload = _pick(data, REPLY_TEMPLATE_WRITE_FIELDS)
        if "content" in payload:
            render_template(str(payload["content"]), _preview_template_values())
        row = self.storage.update_by_id("reply_templates", template_id, payload, tenant_id=context.tenant_id)
        if row and row.get("is_default"):
            self._clear_other_default_templates(context, row["id"])
        return row

    def archive_reply_template(self, context: TenantContext, template_id: str) -> None:
        self._require_tenant_writable(context)
        if not self.storage.get_by_id("reply_templates", template_id, tenant_id=context.tenant_id):
            raise PermissionError("reply template not found")
        require_permission(context, Permission.REPLY_RULE_WRITE)
        self.storage.update_by_id("reply_templates", template_id, {"enabled": False, "archived_at": utc_now()}, tenant_id=context.tenant_id)

    def copy_reply_template(self, context: TenantContext, template_id: str) -> dict[str, Any]:
        source = self.storage.get_by_id("reply_templates", template_id, tenant_id=context.tenant_id)
        if not source:
            raise PermissionError("reply template not found")
        payload = _pick(source, REPLY_TEMPLATE_WRITE_FIELDS)
        payload["name"] = f"{source['name']} Copy"
        payload["is_default"] = False
        return self.create_reply_template(context, payload)

    def preview_reply_template(self, context: TenantContext, data: dict[str, Any]) -> dict[str, Any]:
        template = self.storage.get_by_id("reply_templates", data["template_id"], tenant_id=context.tenant_id) if data.get("template_id") else None
        content = str(data.get("content") or (template or {}).get("content") or "")
        campaign = self.storage.get_by_id("campaigns", data.get("campaign_id"), tenant_id=context.tenant_id) if data.get("campaign_id") else {}
        comment = data.get("comment") or {}
        rendered = render_template(content, self._template_values(context, campaign or {}, comment))
        return {"rendered": rendered, "system_send_enabled": self._system_send_enabled()}

    def list_reply_match_rules(self, context: TenantContext, *, campaign_id: str | None = None) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {"archived_at": None}
        if campaign_id:
            self._require_campaign(context, campaign_id)
            filters["campaign_id"] = campaign_id
        return self.storage.list("reply_match_rules", tenant_id=context.tenant_id, filters=filters, limit=200, order_by=["priority", "created_at"])

    def create_reply_match_rule(self, context: TenantContext, data: dict[str, Any]) -> dict[str, Any]:
        self._require_tenant_writable(context)
        require_permission(context, Permission.REPLY_RULE_WRITE)
        payload = {"enabled": True, "priority": 100, "contains_any_json": [], "contains_all_json": [], "author_exclude_json": [], **_pick(data, REPLY_MATCH_RULE_WRITE_FIELDS)}
        if payload.get("campaign_id"):
            self._require_campaign(context, payload["campaign_id"])
        if payload.get("reply_template_id") and not self.storage.get_by_id("reply_templates", payload["reply_template_id"], tenant_id=context.tenant_id):
            raise PermissionError("reply template not found")
        match_comment({"text": "test", "author_name": "preview", "fingerprint": "preview"}, {}, [payload])
        return self.storage.insert("reply_match_rules", {**payload, "tenant_id": context.tenant_id, "created_by": context.user_id})

    def update_reply_match_rule(self, context: TenantContext, rule_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        self._require_tenant_writable(context)
        current = self.storage.get_by_id("reply_match_rules", rule_id, tenant_id=context.tenant_id)
        if not current:
            return None
        require_permission(context, Permission.REPLY_RULE_WRITE)
        payload = _pick(data, REPLY_MATCH_RULE_WRITE_FIELDS)
        merged = {**current, **payload}
        match_comment({"text": "test", "author_name": "preview", "fingerprint": "preview"}, {}, [merged])
        return self.storage.update_by_id("reply_match_rules", rule_id, payload, tenant_id=context.tenant_id)

    def delete_reply_match_rule(self, context: TenantContext, rule_id: str) -> None:
        self._require_tenant_writable(context)
        if not self.storage.get_by_id("reply_match_rules", rule_id, tenant_id=context.tenant_id):
            raise PermissionError("reply match rule not found")
        require_permission(context, Permission.REPLY_RULE_WRITE)
        self.storage.update_by_id("reply_match_rules", rule_id, {"enabled": False, "archived_at": utc_now()}, tenant_id=context.tenant_id)

    def test_reply_match_rule(self, context: TenantContext, data: dict[str, Any]) -> dict[str, Any]:
        campaign = self.storage.get_by_id("campaigns", data.get("campaign_id"), tenant_id=context.tenant_id) if data.get("campaign_id") else {}
        rule = {"id": "preview", "name": data.get("name") or "Preview", "enabled": True, **_pick(data, REPLY_MATCH_RULE_WRITE_FIELDS)}
        result = match_comment({"text": data.get("comment_text") or "", "author_name": data.get("author_name") or "", "fingerprint": "preview"}, campaign or {}, [rule])
        return result.__dict__

    def list_reply_candidates(self, context: TenantContext, filters: dict[str, Any] | None = None, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        allowed = {"campaign_id", "execution_id", "reply_plan_id", "status"}
        safe_filters = {key: value for key, value in (filters or {}).items() if key in allowed}
        rows = self.storage.list("reply_candidates", tenant_id=context.tenant_id, filters=safe_filters, limit=_safe_limit(limit), offset=offset)
        total = self.storage.count("reply_candidates", tenant_id=context.tenant_id, filters=safe_filters)
        return {"items": rows, "limit": _safe_limit(limit), "offset": offset, "total": total}

    def approve_reply_candidate(self, context: TenantContext, candidate_id: str) -> dict[str, Any]:
        candidate = self._require_reply_candidate(context, candidate_id)
        self._require_reply_approval_role(context)
        if candidate["status"] in {"approved", "sent"}:
            return candidate
        if candidate["status"] not in {"pending_approval", "blocked"}:
            raise ServiceConflictError("candidate_not_approvable")
        row = self.storage.update_by_id("reply_candidates", candidate_id, {"status": "approved", "approved_by": context.user_id, "approved_at": utc_now(), "blocked_reason": None}, tenant_id=context.tenant_id) or candidate
        self.audit.record(action="reply_candidate.approve", resource_type="reply_candidate", resource_id=candidate_id, tenant_id=context.tenant_id, user_id=context.user_id)
        return row

    def reject_reply_candidate(self, context: TenantContext, candidate_id: str, reason: str | None = None) -> dict[str, Any]:
        candidate = self._require_reply_candidate(context, candidate_id)
        self._require_reply_approval_role(context)
        row = self.storage.update_by_id("reply_candidates", candidate_id, {"status": "rejected", "blocked_reason": reason or "rejected", "rejected_by": context.user_id, "rejected_at": utc_now()}, tenant_id=context.tenant_id) or candidate
        self.audit.record(action="reply_candidate.reject", resource_type="reply_candidate", resource_id=candidate_id, tenant_id=context.tenant_id, user_id=context.user_id)
        return row

    def update_reply_candidate_content(self, context: TenantContext, candidate_id: str, content: str) -> dict[str, Any]:
        candidate = self._require_reply_candidate(context, candidate_id)
        self._require_reply_approval_role(context)
        if not content.strip() or len(content) > 2000:
            raise ValueError("rendered_reply_invalid")
        return self.storage.update_by_id("reply_candidates", candidate_id, {"rendered_reply_text": content, "status": "pending_approval"}, tenant_id=context.tenant_id) or candidate

    def list_reply_plans(self, context: TenantContext, filters: dict[str, Any] | None = None, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        allowed = {"campaign_id", "execution_id", "status"}
        safe_filters = {key: value for key, value in (filters or {}).items() if key in allowed}
        rows = self.storage.list("reply_plans", tenant_id=context.tenant_id, filters=safe_filters, limit=_safe_limit(limit), offset=offset)
        total = self.storage.count("reply_plans", tenant_id=context.tenant_id, filters=safe_filters)
        return {"items": rows, "limit": _safe_limit(limit), "offset": offset, "total": total}

    def approve_reply_plan(self, context: TenantContext, plan_id: str) -> dict[str, Any]:
        plan = self._require_reply_plan(context, plan_id)
        self._require_reply_approval_role(context, automatic_allowed=True)
        if plan["status"] in {"approved", "pending_approval"}:
            status = "approved"
        elif plan["status"] == "executed":
            return plan
        else:
            raise ServiceConflictError("plan_not_approvable")
        row = self.storage.update_by_id("reply_plans", plan_id, {"status": status, "approved_by": context.user_id, "approved_at": utc_now()}, tenant_id=context.tenant_id) or plan
        self.audit.record(action="reply_plan.approve", resource_type="reply_plan", resource_id=plan_id, tenant_id=context.tenant_id, user_id=context.user_id)
        return row

    def cancel_reply_plan(self, context: TenantContext, plan_id: str) -> dict[str, Any]:
        plan = self._require_reply_plan(context, plan_id)
        self._require_reply_approval_role(context, automatic_allowed=True)
        return self.storage.update_by_id("reply_plans", plan_id, {"status": "cancelled"}, tenant_id=context.tenant_id) or plan

    def execute_reply_plan(self, context: TenantContext, plan_id: str) -> dict[str, Any]:
        plan = self._require_reply_plan(context, plan_id)
        self._require_reply_approval_role(context, automatic_allowed=True)
        guard = self._reply_send_guard(context, plan)
        if guard:
            row = self.storage.update_by_id("reply_plans", plan_id, {"status": "blocked", "blocked_reason": guard}, tenant_id=context.tenant_id) or plan
            self.storage.insert_ignore("reply_records", {"tenant_id": context.tenant_id, "reply_plan_id": plan_id, "campaign_id": plan["campaign_id"], "platform_account_id": plan["platform_account_id"], "comment_id": None, "reply_text": "", "status": "blocked", "verified": False, "error_type": guard, "error_message": guard, "idempotency_key": f"{plan_id}:{guard}"})
            return row
        return self.storage.update_by_id("reply_plans", plan_id, {"status": "executed", "executed_at": utc_now()}, tenant_id=context.tenant_id) or plan

    def list_reply_records(self, context: TenantContext, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        rows = self.storage.list("reply_records", tenant_id=context.tenant_id, limit=_safe_limit(limit), offset=offset)
        total = self.storage.count("reply_records", tenant_id=context.tenant_id)
        return {"items": rows, "limit": _safe_limit(limit), "offset": offset, "total": total}

    def generate_reply_plan_for_execution(self, context: TenantContext, execution_id: str) -> dict[str, Any] | None:
        execution = self._require_execution(context, execution_id)
        campaign = self._require_campaign(context, execution["campaign_id"])
        if campaign.get("reply_mode") == "disabled":
            return None
        account = self._require_platform_account(context, campaign["platform_account_id"])
        existing = self.storage.find_one("reply_plans", {"tenant_id": context.tenant_id, "execution_id": execution_id})
        plan = existing or self.storage.insert(
            "reply_plans",
            {
                "tenant_id": context.tenant_id,
                "campaign_id": campaign["id"],
                "execution_id": execution_id,
                "platform_account_id": account["id"],
                "status": "pending_approval" if campaign.get("reply_mode") == "manual_approval" else "approved",
                "reply_mode": campaign.get("reply_mode") or "manual_approval",
                "total_candidates": 0,
                "approved_count": 0,
                "sent_count": 0,
                "failed_count": 0,
                "created_by": context.user_id if self.storage.get_by_id("users", context.user_id) else None,
            },
        )
        rules = self.list_reply_match_rules(context, campaign_id=campaign["id"])
        comments = comments_from_scan_artifacts(self.artifacts_root, context.tenant_id, execution_id)
        inserted = 0
        for comment in comments:
            key = build_candidate_key(context.tenant_id, campaign["id"], comment)
            if self.storage.find_one("reply_candidates", {"tenant_id": context.tenant_id, "campaign_id": campaign["id"], "idempotency_key": key}):
                continue
            result = match_comment(comment, campaign, rules)
            if not result.matched:
                continue
            template = self._select_reply_template(context, result.template_id, campaign)
            if not template:
                status = "blocked"
                rendered = None
                blocked = "no_template"
            else:
                rendered = render_template(template["content"], self._template_values(context, campaign, comment))
                status = "pending_approval" if campaign.get("reply_mode") == "manual_approval" else "approved"
                blocked = None
            self.storage.insert(
                "reply_candidates",
                {
                    "tenant_id": context.tenant_id,
                    "campaign_id": campaign["id"],
                    "execution_id": execution_id,
                    "reply_plan_id": plan["id"],
                    "platform_account_id": account["id"],
                    "platform": account["platform"],
                    "comment_id": comment.get("comment_id"),
                    "comment_fingerprint": comment.get("fingerprint") or key,
                    "author_name": comment.get("author_name"),
                    "comment_text": comment.get("text"),
                    "source_content_url": comment.get("source_content_url"),
                    "direct_comment_url": comment.get("direct_comment_url") or comment.get("comment_url"),
                    "matched_rule_id": result.rule_id,
                    "matched_rule_name": result.matched_rule,
                    "reply_template_id": (template or {}).get("id"),
                    "rendered_reply_text": rendered,
                    "status": status,
                    "blocked_reason": blocked,
                    "idempotency_key": key,
                },
            )
            inserted += 1
        candidates = self.storage.list("reply_candidates", tenant_id=context.tenant_id, filters={"reply_plan_id": plan["id"]}, limit=1000)
        approved = sum(1 for row in candidates if row["status"] == "approved")
        return self.storage.update_by_id("reply_plans", plan["id"], {"total_candidates": len(candidates), "approved_count": approved, "blocked_reason": "no_candidates" if not candidates else None}, tenant_id=context.tenant_id) or plan

    def list_reply_rules(self, context: TenantContext) -> list[dict[str, Any]]:
        return self.storage.list("reply_rules", tenant_id=context.tenant_id)

    def create_reply_rule(self, context: TenantContext, data: dict[str, Any]) -> dict[str, Any]:
        self._require_tenant_writable(context)
        payload = _pick(data, REPLY_RULE_WRITE_FIELDS)
        self._require_campaign(context, payload["campaign_id"])
        require_permission(context, Permission.REPLY_RULE_WRITE)
        if payload.get("approval_mode") == "auto":
            raise ValueError("auto approval is not available")
        return self.storage.insert("reply_rules", {"enabled": True, **payload, "tenant_id": context.tenant_id, "approval_mode": "manual"})

    def update_reply_rule(self, context: TenantContext, rule_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        self._require_tenant_writable(context)
        if not self.storage.get_by_id("reply_rules", rule_id, tenant_id=context.tenant_id):
            return None
        require_permission(context, Permission.REPLY_RULE_WRITE)
        if data.get("approval_mode") == "auto":
            raise ValueError("auto approval is not available")
        return self.storage.update_by_id("reply_rules", rule_id, _pick(data, REPLY_RULE_WRITE_FIELDS - {"campaign_id"}), tenant_id=context.tenant_id)

    def delete_reply_rule(self, context: TenantContext, rule_id: str) -> None:
        self._require_tenant_writable(context)
        if not self.storage.get_by_id("reply_rules", rule_id, tenant_id=context.tenant_id):
            raise PermissionError("reply rule not found")
        require_permission(context, Permission.REPLY_RULE_WRITE)
        self.storage.delete_by_id("reply_rules", rule_id, tenant_id=context.tenant_id)

    def list_executions(self, context: TenantContext, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        limit = _safe_limit(limit)
        return self.storage.list("executions", tenant_id=context.tenant_id, limit=limit, offset=max(offset, 0))

    def get_execution(self, context: TenantContext, execution_id: str) -> dict[str, Any] | None:
        execution = self.storage.get_by_id("executions", execution_id, tenant_id=context.tenant_id)
        if execution:
            queue = self.storage.find_one("execution_queue_items", {"tenant_id": context.tenant_id, "execution_id": execution_id})
            execution["queue"] = queue
        return execution

    def list_execution_keywords(self, context: TenantContext, execution_id: str) -> list[dict[str, Any]]:
        self._require_execution(context, execution_id)
        return self.storage.list("execution_keywords", tenant_id=context.tenant_id, filters={"execution_id": execution_id}, limit=1000, order_by=["created_at"])

    def cancel_execution(self, context: TenantContext, execution_id: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        execution = self._require_execution(context, execution_id)
        require_permission(context, Permission.EXECUTION_CANCEL)
        if execution["status"] in {"completed", "partial", "failed", "cancelled"}:
            return execution
        queue = self.storage.find_one("execution_queue_items", {"tenant_id": context.tenant_id, "execution_id": execution_id})
        now = utc_now()
        if execution["status"] == "queued":
            if queue:
                self.storage.update_by_id("execution_queue_items", queue["id"], {"status": "cancelled", "finished_at": now}, tenant_id=context.tenant_id)
            return self.storage.update_by_id("executions", execution_id, {"status": "cancelled", "finished_at": now, "progress_percent": 100}, tenant_id=context.tenant_id) or execution
        return self.storage.update_by_id(
            "executions",
            execution_id,
            {"cancel_requested": True, "cancel_requested_at": now},
            tenant_id=context.tenant_id,
        ) or execution

    def get_campaign_schedule(self, context: TenantContext, campaign_id: str) -> dict[str, Any] | None:
        self._require_campaign(context, campaign_id)
        return self.storage.find_one("campaign_schedules", {"tenant_id": context.tenant_id, "campaign_id": campaign_id})

    def put_campaign_schedule(self, context: TenantContext, campaign_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_campaign(context, campaign_id)
        require_permission(context, Permission.SCHEDULE_WRITE)
        if data.get("enabled"):
            self.quota.require_feature(context.tenant_id, "allow_scheduler")
        schedule_type = str(data.get("schedule_type") or "manual")
        if schedule_type not in {"manual", "interval", "daily"}:
            raise ValueError("invalid schedule_type")
        timezone_name = str(data.get("timezone") or "UTC")
        _zone(timezone_name)
        enabled = bool(data.get("enabled")) and schedule_type != "manual"
        payload = {
            "tenant_id": context.tenant_id,
            "campaign_id": campaign_id,
            "enabled": enabled,
            "schedule_type": schedule_type,
            "interval_minutes": int(data["interval_minutes"]) if data.get("interval_minutes") else None,
            "daily_time": data.get("daily_time"),
            "timezone": timezone_name,
            "next_run_at": self._compute_next_run(schedule_type, timezone_name, interval_minutes=data.get("interval_minutes"), daily_time=data.get("daily_time")),
        }
        existing = self.storage.find_one("campaign_schedules", {"tenant_id": context.tenant_id, "campaign_id": campaign_id})
        if existing:
            return self.storage.update_by_id("campaign_schedules", existing["id"], payload, tenant_id=context.tenant_id) or existing
        return self.storage.insert("campaign_schedules", payload)

    def disable_campaign_schedule(self, context: TenantContext, campaign_id: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_campaign(context, campaign_id)
        require_permission(context, Permission.SCHEDULE_WRITE)
        schedule = self.get_campaign_schedule(context, campaign_id)
        if not schedule:
            return self.put_campaign_schedule(context, campaign_id, {"schedule_type": "manual", "enabled": False, "timezone": "UTC"})
        return self.storage.update_by_id("campaign_schedules", schedule["id"], {"enabled": False, "schedule_type": "manual", "next_run_at": None}, tenant_id=context.tenant_id) or schedule

    def dashboard_summary(self, context: TenantContext) -> dict[str, Any]:
        queue_counts = self.storage.queue_counts(tenant_id=context.tenant_id)
        return {
            "active_campaigns": self._count(context, "campaigns", {"status": "active"}),
            "connected_platform_accounts": self._count(context, "platform_accounts", {"connection_status": "connected"}),
            "leads_today": self._count(context, "leads", date_field="discovered_at", since_today=True),
            "new_leads": self._count(context, "leads", {"status": "new"}),
            "high_intent_leads": self._count(context, "leads", {"final_intent_level": "high"}),
            "executions_today": self._count(context, "executions", date_field="started_at", since_today=True),
            "tokens_today": self._sum_tokens(context, since_today=True),
            "tokens_this_month": self._sum_tokens(context, month_utc=True),
            "queued_tasks": queue_counts.get("queued", 0) + queue_counts.get("retry_waiting", 0),
            "running_tasks": queue_counts.get("running", 0),
            "failed_tasks": queue_counts.get("failed", 0),
            "auto_tasks_today": self._count(context, "executions", {"trigger_type": "scheduled"}, date_field="created_at", since_today=True),
            "pending_replies": self._count(context, "reply_candidates", {"status": "pending_approval"}),
            "today_replied": self._count(context, "reply_records", {"status": "sent"}, date_field="created_at", since_today=True),
            "today_failed_replies": self._count(context, "reply_records", {"status": "failed"}, date_field="created_at", since_today=True),
            "reply_success_rate": self._reply_success_rate(context),
            "system_send_enabled": self._system_send_enabled(),
            "reply_safety_message": "" if self._system_send_enabled() else "回复发送当前处于关闭状态",
            "recent_executions": self.list_executions(context, limit=5),
            "latest_leads": self.list_leads(context, limit=5)["items"],
        }

    def token_usage_summary(self, context: TenantContext) -> dict[str, Any]:
        return {
            "today": self._sum_tokens(context, since_today=True),
            "last_7_days": self._sum_tokens(context, since_days=7),
            "this_month": self._sum_tokens(context, month_utc=True),
        }

    def token_usage_details(self, context: TenantContext, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        limit = _safe_limit(limit)
        by_model = self.storage.grouped_sum("token_usage", "model", "total_tokens", tenant_id=context.tenant_id)
        by_campaign = self.storage.grouped_sum("token_usage", "campaign_id", "total_tokens", tenant_id=context.tenant_id)
        for row in by_campaign:
            campaign_id = row.get("campaign_id")
            campaign = self.storage.get_by_id("campaigns", campaign_id) if isinstance(campaign_id, str) else None
            row["campaign_name"] = campaign.get("name") if campaign and campaign.get("tenant_id") == context.tenant_id else None
        return {
            "items": self.storage.list("token_usage", tenant_id=context.tenant_id, limit=limit, offset=max(offset, 0)),
            "limit": limit,
            "offset": max(offset, 0),
            "total": self.storage.count("token_usage", tenant_id=context.tenant_id),
            "by_model": by_model,
            "by_campaign": by_campaign,
        }

    async def run_campaign(self, context: TenantContext, campaign_id: str) -> dict[str, Any]:
        execution = self.enqueue_campaign_execution(context, campaign_id, trigger_type="manual")
        return {"execution_id": execution["id"], "status": "queued", "send_disabled": True}

    def enqueue_campaign_execution(self, context: TenantContext, campaign_id: str, *, trigger_type: str, schedule_trigger_key: str | None = None) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self.quota.check_quota(context.tenant_id, "monthly_executions")
        self.quota.check_quota(context.tenant_id, "monthly_tokens", increment=0)
        self.quota.warn_all(context.tenant_id)
        self._require_runtime_available()
        campaign = self._require_campaign(context, campaign_id)
        require_permission(context, Permission.EXECUTION_RUN)
        if schedule_trigger_key and self.storage.find_one(
            "execution_queue_items",
            {"tenant_id": context.tenant_id, "schedule_trigger_key": schedule_trigger_key},
        ):
            raise ValueError("schedule window already enqueued")
        queue_counts = self.storage.queue_counts(tenant_id=context.tenant_id)
        queued_count = queue_counts.get("queued", 0) + queue_counts.get("retry_waiting", 0)
        if queued_count >= self.max_queued_executions_per_tenant:
            raise ValueError("queue_limit_reached")
        account = self.storage.get_by_id("platform_accounts", campaign["platform_account_id"], tenant_id=context.tenant_id)
        if not account:
            raise PermissionError("platform account not found")
        keywords = self.storage.list(
            "campaign_keywords",
            tenant_id=context.tenant_id,
            filters={"campaign_id": campaign_id, "enabled": True},
            limit=1000,
            order_by=["priority", "created_at"],
        )
        if not keywords:
            raise ValueError("campaign has no enabled keyword")
        snapshot = self.campaigns.config_snapshot(campaign, keywords)
        execution = self.storage.insert(
            "executions",
            {
                "tenant_id": context.tenant_id,
                "campaign_id": campaign_id,
                "platform": account["platform"],
                "status": "queued",
                "trigger_type": trigger_type,
                "stage": "queued",
                "total_keywords": len(keywords),
                "send_disabled": True,
                "config_snapshot": snapshot,
            },
        )
        queue = self.storage.insert_ignore(
            "execution_queue_items",
            {
                "tenant_id": context.tenant_id,
                "campaign_id": campaign_id,
                "execution_id": execution["id"],
                "status": "queued",
                "priority": 100,
                "schedule_trigger_key": schedule_trigger_key,
                "queued_at": utc_now(),
                "run_after": utc_now(),
            },
        )
        if queue is None:
            self.storage.delete_by_id("executions", execution["id"], tenant_id=context.tenant_id)
            raise ValueError("schedule window already enqueued")
        return execution

    async def run_queue_item(self, queue_item: dict[str, Any]) -> dict[str, Any]:
        context = TenantContext(tenant_id=queue_item["tenant_id"], user_id="worker", role="worker")
        execution = self._require_execution(context, queue_item["execution_id"])
        campaign = self._require_campaign(context, queue_item["campaign_id"])
        snapshot = execution.get("config_snapshot") or {}
        execution_campaign = {**campaign, **{key: value for key, value in snapshot.items() if key != "keywords"}}
        if execution_campaign.get("llm_enabled") and self.config and not (
            self.config.llm_endpoint and self.config.llm_api_key and self.config.llm_model
        ):
            return self._finish_queue_failure(
                queue_item,
                execution,
                "llm_configuration_missing",
                "LLM endpoint, API key, and model must be configured",
            )
        account = self.storage.get_by_id("platform_accounts", snapshot.get("platform_account_id") or campaign["platform_account_id"], tenant_id=context.tenant_id)
        if not account:
            return self._finish_queue_failure(queue_item, execution, "platform_account_not_connected", "platform account not found")
        try:
            runtime = self._preflight_runtime(context, account, campaign["id"], create_failed_execution=False)
        except ValueError as exc:
            return self._finish_queue_error(queue_item, execution, str(exc), str(exc))
        lock_key = runtime["id"]
        if lock_key in self._runtime_locks:
            return self._retry_queue_item(queue_item, execution, "runtime_locked", "same platform account already has an active run")
        provider = self.providers.get(account["platform"])
        if not provider:
            return self._finish_queue_failure(queue_item, execution, "provider_not_registered", "provider not registered")
        run_context = PlatformRunContext(
            tenant_id=context.tenant_id,
            platform_account_id=account["id"],
            runtime_id=runtime["id"],
            cdp_url=runtime["cdp_url"],
            profile_path=runtime["profile_path"],
            target_policy=campaign["target_policy"],
            send_disabled=True,
        )
        keywords = snapshot.get("keywords") or []
        if not keywords:
            return self._finish_queue_failure(queue_item, execution, "no_enabled_keyword", "campaign has no enabled keyword")
        database_lock = self.storage.acquire_runtime_lock(lock_key)
        if database_lock is None:
            return self._retry_queue_item(queue_item, execution, "runtime_locked", "same browser runtime is already in use by another worker")
        if lock_key in self._runtime_locks:
            self.storage.release_runtime_lock(database_lock)
            return self._retry_queue_item(queue_item, execution, "runtime_locked", "same platform account already has an active run")
        self._runtime_locks.add(lock_key)
        self.storage.update_by_id("executions", execution["id"], {"status": "running", "stage": "worker", "started_at": utc_now(), "total_keywords": len(keywords), "progress_percent": 0}, tenant_id=context.tenant_id)
        try:
            completed = 0
            failed = 0
            retryable_failures = 0
            last_retryable_error = ("temporary_error", "temporary provider failure")
            for index, keyword in enumerate(keywords, start=1):
                current = self.storage.get_by_id("executions", execution["id"], tenant_id=context.tenant_id) or execution
                if current.get("cancel_requested"):
                    break
                keyword_row = self.storage.find_one(
                    "execution_keywords",
                    {"tenant_id": context.tenant_id, "execution_id": execution["id"], "keyword": keyword["keyword"]},
                )
                keyword_payload = {
                    "tenant_id": context.tenant_id,
                    "execution_id": execution["id"],
                    "campaign_keyword_id": keyword.get("id"),
                    "keyword": keyword["keyword"],
                    "attempt_number": int(queue_item.get("attempt_count") or 1),
                    "status": "running",
                    "started_at": utc_now(),
                    "finished_at": None,
                    "error_type": None,
                    "error_message": None,
                }
                if keyword_row:
                    keyword_row = self.storage.update_by_id("execution_keywords", keyword_row["id"], keyword_payload, tenant_id=context.tenant_id) or keyword_row
                else:
                    keyword_row = self.storage.insert("execution_keywords", keyword_payload)
                self.storage.update_by_id("executions", execution["id"], {"current_keyword": keyword["keyword"], "progress_percent": int((index - 1) * 100 / len(keywords))}, tenant_id=context.tenant_id)
                try:
                    result = await provider.run_campaign(self._provider_request(context, execution_campaign, keyword["keyword"], run_context, execution["id"]))
                    summary = _keyword_summary(result)
                    status = "failed" if result.get("status") in {"failed", "not_implemented"} else "completed"
                    if status == "completed":
                        completed += 1
                        persist_orchestrator_result(
                            self.storage,
                            tenant_id=context.tenant_id,
                            campaign_id=campaign["id"],
                            platform_account_id=account["id"],
                            platform=account["platform"],
                            result=result,
                            execution_id=execution["id"],
                            execution_keyword_id=keyword_row["id"],
                            keyword=keyword["keyword"],
                            attempt_number=int(queue_item.get("attempt_count") or 1),
                            input_cost_per_1m=self.config.llm_input_cost_per_1m if self.config else None,
                            output_cost_per_1m=self.config.llm_output_cost_per_1m if self.config else None,
                        )
                    else:
                        failed += 1
                        if _is_retryable_error(result.get("error_type"), result.get("error_message")):
                            retryable_failures += 1
                            last_retryable_error = (str(result.get("error_type") or "temporary_error"), str(result.get("error_message") or "temporary provider failure"))
                    self.storage.update_by_id("execution_keywords", keyword_row["id"], {"status": status, "finished_at": utc_now(), **summary, "error_type": result.get("error_type"), "error_message": result.get("error_message")}, tenant_id=context.tenant_id)
                except Exception as exc:
                    failed += 1
                    if _is_retryable_error(type(exc).__name__, str(exc)):
                        retryable_failures += 1
                        last_retryable_error = (type(exc).__name__, str(exc))
                    self.storage.update_by_id("execution_keywords", keyword_row["id"], {"status": "failed", "finished_at": utc_now(), "error_type": type(exc).__name__, "error_message": str(exc)}, tenant_id=context.tenant_id)
                self._update_execution_aggregate(context, execution["id"], total=len(keywords), completed=completed, failed=failed)
            if completed == 0 and failed == len(keywords) and retryable_failures == failed:
                for row in self.storage.list(
                    "execution_keywords",
                    tenant_id=context.tenant_id,
                    filters={"execution_id": execution["id"]},
                    limit=1000,
                ):
                    if not self.storage.find_one("token_usage", {"execution_keyword_id": row["id"]}):
                        self.storage.delete_by_id("execution_keywords", row["id"], tenant_id=context.tenant_id)
                self.storage.update_by_id("executions", execution["id"], {"completed_keywords": 0, "failed_keywords": 0, "current_keyword": None, "progress_percent": 0}, tenant_id=context.tenant_id)
                return self._retry_queue_item(queue_item, execution, *last_retryable_error)
            final_execution = self.storage.get_by_id("executions", execution["id"], tenant_id=context.tenant_id) or execution
            status = "cancelled" if final_execution.get("cancel_requested") else ("completed" if completed == len(keywords) else "partial" if completed else "failed")
            self._update_execution_aggregate(context, execution["id"], total=len(keywords), completed=completed, failed=failed, status=status, finished=True)
            if status in {"completed", "partial"}:
                self.generate_reply_plan_for_execution(context, execution["id"])
            return self.storage.update_by_id("execution_queue_items", queue_item["id"], {"status": "completed" if status in {"completed", "partial"} else status, "finished_at": utc_now()}, tenant_id=context.tenant_id) or queue_item
        except Exception as exc:
            self.storage.update_by_id("browser_runtimes", runtime["id"], {"status": "unhealthy", "last_error": "campaign run failed"}, tenant_id=context.tenant_id)
            return self._finish_queue_error(queue_item, execution, type(exc).__name__, str(exc))
        finally:
            self._runtime_locks.discard(lock_key)
            self.storage.release_runtime_lock(database_lock)

    def _provider_request(self, context: TenantContext, campaign: dict[str, Any], keyword: str, run_context: PlatformRunContext, execution_id: str) -> ProviderRunRequest:
        execution_root = safe_artifact_path(
            self.artifacts_root,
            "tenants",
            context.tenant_id,
            "executions",
            execution_id,
        )
        return ProviderRunRequest(
            tenant_id=context.tenant_id,
            campaign_id=campaign["id"],
            keyword=keyword,
            target_policy=campaign["target_policy"],
            max_contents=int(campaign["max_contents"]),
            max_comments=int(campaign["max_comments"]),
            min_confidence=float(campaign["min_confidence"]),
            max_leads=int(campaign["max_leads"]),
            daily_limit=int(campaign["daily_limit"]),
            llm_enabled=bool(campaign["llm_enabled"]),
            history_path=str(execution_root / "reply_history.jsonl"),
            runs_root=str(execution_root / "runs"),
            run_context=run_context,
        )

    def _update_execution_aggregate(self, context: TenantContext, execution_id: str, *, total: int, completed: int, failed: int, status: str | None = None, finished: bool = False) -> dict[str, Any] | None:
        rows = self.storage.list("execution_keywords", tenant_id=context.tenant_id, filters={"execution_id": execution_id}, limit=1000)
        payload: dict[str, Any] = {
            "total_keywords": total,
            "completed_keywords": completed,
            "failed_keywords": failed,
            "progress_percent": 100 if finished else int(((completed + failed) * 100) / max(total, 1)),
            "scanned_contents": sum(int(row.get("discovered_contents") or 0) for row in rows),
            "scanned_comments": sum(int(row.get("scanned_comments") or 0) for row in rows),
            "lead_candidates": sum(int(row.get("lead_candidates") or 0) for row in rows),
            "eligible_count": sum(int(row.get("eligible_count") or 0) for row in rows),
            "selected_count": sum(int(row.get("selected_count") or 0) for row in rows),
            "prompt_tokens": sum(int(row.get("prompt_tokens") or 0) for row in rows),
            "completion_tokens": sum(int(row.get("completion_tokens") or 0) for row in rows),
            "total_tokens": sum(int(row.get("total_tokens") or 0) for row in rows),
        }
        if status:
            payload["status"] = status
            payload["stage"] = status
        if finished:
            payload["finished_at"] = utc_now()
            current = self.storage.get_by_id("executions", execution_id, tenant_id=context.tenant_id)
            if current and current.get("started_at"):
                payload["elapsed_ms"] = max(0, int((utc_now() - _dt(current["started_at"])).total_seconds() * 1000))
        updated = self.storage.update_by_id("executions", execution_id, payload, tenant_id=context.tenant_id)
        if finished and updated:
            self.notifications.execution_finished(updated)
            self.quota.warn_all(context.tenant_id)
        return updated

    def _retry_queue_item(self, queue_item: dict[str, Any], execution: dict[str, Any], error_type: str, message: str) -> dict[str, Any]:
        current = self.storage.get_by_id("executions", execution["id"], tenant_id=execution["tenant_id"]) or execution
        if current.get("cancel_requested"):
            return self._cancel_queue_item(queue_item, current)
        attempts = int(queue_item.get("attempt_count") or 0)
        max_attempts = int(queue_item.get("max_attempts") or 3)
        if attempts >= max_attempts:
            return self._finish_queue_failure(queue_item, execution, error_type, message)
        delay = [30, 120, 300][min(max(attempts - 1, 0), 2)]
        self.storage.update_by_id("executions", execution["id"], {"status": "queued", "stage": "retry_waiting", "error_type": error_type, "error_message": message}, tenant_id=execution["tenant_id"])
        return self.storage.update_by_id("execution_queue_items", queue_item["id"], {"status": "retry_waiting", "run_after": utc_now() + timedelta(seconds=delay), "error_type": error_type, "error_message": message}, tenant_id=execution["tenant_id"]) or queue_item

    def _finish_queue_error(self, queue_item: dict[str, Any], execution: dict[str, Any], error_type: str, message: str) -> dict[str, Any]:
        current = self.storage.get_by_id("executions", execution["id"], tenant_id=execution["tenant_id"]) or execution
        if current.get("cancel_requested"):
            return self._cancel_queue_item(queue_item, current)
        if _is_retryable_error(error_type, message):
            return self._retry_queue_item(queue_item, execution, error_type, message)
        return self._finish_queue_failure(queue_item, execution, error_type, message)

    def _finish_queue_failure(self, queue_item: dict[str, Any], execution: dict[str, Any], error_type: str, message: str) -> dict[str, Any]:
        now = utc_now()
        updated = self.storage.update_by_id("executions", execution["id"], {"status": "failed", "stage": "failed", "error_type": error_type, "error_message": message, "finished_at": now, "progress_percent": 100}, tenant_id=execution["tenant_id"])
        if updated:
            self.notifications.execution_finished(updated)
        return self.storage.update_by_id("execution_queue_items", queue_item["id"], {"status": "failed", "finished_at": now, "error_type": error_type, "error_message": message}, tenant_id=execution["tenant_id"]) or queue_item

    def _cancel_queue_item(self, queue_item: dict[str, Any], execution: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        self.storage.update_by_id(
            "executions",
            execution["id"],
            {"status": "cancelled", "stage": "cancelled", "finished_at": now, "progress_percent": 100},
            tenant_id=execution["tenant_id"],
        )
        return self.storage.update_by_id(
            "execution_queue_items",
            queue_item["id"],
            {"status": "cancelled", "finished_at": now},
            tenant_id=execution["tenant_id"],
        ) or queue_item

    def _require_campaign(self, context: TenantContext, campaign_id: str) -> dict[str, Any]:
        campaign = self.storage.get_by_id("campaigns", campaign_id, tenant_id=context.tenant_id)
        if not campaign or campaign.get("deleted_at"):
            raise PermissionError("campaign not found")
        return campaign

    def _require_execution(self, context: TenantContext, execution_id: str) -> dict[str, Any]:
        execution = self.storage.get_by_id("executions", execution_id, tenant_id=context.tenant_id)
        if not execution:
            raise PermissionError("execution not found")
        return execution

    def _require_reply_candidate(self, context: TenantContext, candidate_id: str) -> dict[str, Any]:
        candidate = self.storage.get_by_id("reply_candidates", candidate_id, tenant_id=context.tenant_id)
        if not candidate:
            raise PermissionError("reply candidate not found")
        return candidate

    def _require_reply_plan(self, context: TenantContext, plan_id: str) -> dict[str, Any]:
        plan = self.storage.get_by_id("reply_plans", plan_id, tenant_id=context.tenant_id)
        if not plan:
            raise PermissionError("reply plan not found")
        return plan

    def _require_platform_account(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        account = self.storage.get_by_id("platform_accounts", account_id, tenant_id=context.tenant_id)
        if not account:
            raise PermissionError("platform account not found")
        return account

    def _require_reply_approval_role(self, context: TenantContext, *, automatic_allowed: bool = False) -> None:
        if context.role in {"owner", "admin"}:
            return
        if context.role == "member" and not automatic_allowed:
            return
        raise PermissionError("permission denied")

    def _clear_other_default_templates(self, context: TenantContext, template_id: str) -> None:
        for row in self.storage.list("reply_templates", tenant_id=context.tenant_id, filters={"is_default": True}, limit=200):
            if row["id"] != template_id:
                self.storage.update_by_id("reply_templates", row["id"], {"is_default": False}, tenant_id=context.tenant_id)

    def _template_values(self, context: TenantContext, campaign: dict[str, Any] | None, comment: dict[str, Any]) -> dict[str, Any]:
        tenant = self.storage.get_by_id("tenants", context.tenant_id) or {}
        campaign = campaign or {}
        return {
            "whatsapp": campaign.get("default_whatsapp") or tenant.get("default_whatsapp"),
            "email": campaign.get("default_email") or tenant.get("default_email"),
            "website": campaign.get("default_website") or tenant.get("default_website"),
            "contact": campaign.get("default_contact_text") or tenant.get("default_contact_text"),
            "campaign_name": campaign.get("name") or "Campaign",
            "keyword": comment.get("keyword") or "keyword",
            "author_name": comment.get("author_name") or "Customer",
        }

    def _select_reply_template(self, context: TenantContext, rule_template_id: str | None, campaign: dict[str, Any]) -> dict[str, Any] | None:
        candidates = [rule_template_id, campaign.get("default_reply_template_id")]
        for template_id in candidates:
            if template_id:
                template = self.storage.get_by_id("reply_templates", template_id, tenant_id=context.tenant_id)
                if template and template.get("enabled") and not template.get("archived_at"):
                    return template
        return self.storage.find_one("reply_templates", {"tenant_id": context.tenant_id, "enabled": True, "is_default": True, "archived_at": None}, order_by=["priority", "created_at"])

    def _reply_send_guard(self, context: TenantContext, plan: dict[str, Any]) -> str | None:
        campaign = self._require_campaign(context, plan["campaign_id"])
        tenant = self.storage.get_by_id("tenants", context.tenant_id) or {}
        account = self._require_platform_account(context, plan["platform_account_id"])
        if not self._system_send_enabled():
            return "system_send_disabled"
        if not tenant.get("tenant_reply_enabled"):
            return "tenant_reply_disabled"
        if campaign.get("reply_mode") == "disabled":
            return "campaign_reply_disabled"
        if campaign.get("reply_mode") == "manual_approval" and plan.get("status") != "approved":
            return "manual_approval_required"
        try:
            self._preflight_runtime(context, account, campaign["id"], create_failed_execution=False)
        except ValueError as exc:
            return str(exc)
        approved = self.storage.count("reply_candidates", tenant_id=context.tenant_id, filters={"reply_plan_id": plan["id"], "status": "approved"})
        if approved <= 0:
            return "no_approved_candidates"
        today_sent = self.storage.count("reply_records", tenant_id=context.tenant_id, filters={"campaign_id": campaign["id"], "status": "sent"}, date_field="created_at", since=_today_start())
        if today_sent >= int(campaign.get("reply_daily_limit") or 30):
            return "daily_limit_reached"
        return None

    def _system_send_enabled(self) -> bool:
        return bool(self.config and self.config.system_send_enabled)

    def _reply_success_rate(self, context: TenantContext) -> float:
        sent = self._count(context, "reply_records", {"status": "sent"}, date_field="created_at", since_today=True)
        failed = self._count(context, "reply_records", {"status": "failed"}, date_field="created_at", since_today=True)
        total = sent + failed
        return round(sent / total, 4) if total else 0.0

    def _require_runtime_available(self) -> None:
        self.runtimes.require_available()

    def _preflight_runtime(self, context: TenantContext, account: dict[str, Any], campaign_id: str, *, create_failed_execution: bool = True) -> dict[str, Any]:
        runtime = self.runtime_registry.get_runtime(context, account["id"])
        if not runtime:
            if create_failed_execution:
                execution = self._failed_execution(context, campaign_id, account["platform"], "platform_account_not_connected", "platform account has no browser runtime")
                raise ValueError(execution["error_type"])
            raise ValueError("platform_account_not_connected")
        if runtime["status"] == "stopped":
            runtime = self.runtime_registry.start_runtime(context, account["id"])
        health = self.runtime_registry.health_check(context, runtime["id"])
        runtime = self.storage.get_by_id("browser_runtimes", runtime["id"], tenant_id=context.tenant_id) or runtime
        if not health["reachable"]:
            if create_failed_execution:
                self._failed_execution(context, campaign_id, account["platform"], "cdp_unreachable", "browser runtime CDP is unreachable")
            raise ValueError("cdp_unreachable")
        if runtime["status"] not in {"running"}:
            if create_failed_execution:
                self._failed_execution(context, campaign_id, account["platform"], "runtime_not_running", "browser runtime is not running")
            raise ValueError("runtime_not_running")
        if account.get("login_status") != "logged_in":
            if create_failed_execution:
                self._failed_execution(context, campaign_id, account["platform"], "login_required", "platform account login is required")
            raise ValueError("login_required")
        return runtime

    def _compute_next_run(self, schedule_type: str, timezone_name: str, *, interval_minutes: Any = None, daily_time: Any = None) -> datetime | None:
        now = utc_now()
        zone = _zone(timezone_name)
        if schedule_type == "manual":
            return None
        if schedule_type == "interval":
            minutes = int(interval_minutes or 360)
            if minutes <= 0:
                raise ValueError("interval_minutes must be positive")
            return now + timedelta(minutes=minutes)
        if schedule_type == "daily":
            hour, minute = _parse_daily_time(str(daily_time or "09:00"))
            local_now = now.astimezone(zone)
            candidate = datetime.combine(local_now.date(), time(hour, minute), tzinfo=zone)
            if candidate <= local_now:
                candidate += timedelta(days=1)
            return candidate.astimezone(timezone.utc)
        raise ValueError("invalid schedule_type")

    def _failed_execution(self, context: TenantContext, campaign_id: str, platform: str, error_type: str, message: str) -> dict[str, Any]:
        return self.storage.insert(
            "executions",
            {
                "tenant_id": context.tenant_id,
                "campaign_id": campaign_id,
                "platform": platform,
                "status": "failed",
                "stage": "preflight",
                "send_disabled": True,
                "error_type": error_type,
                "error_message": message,
                "started_at": utc_now(),
                "finished_at": utc_now(),
            },
        )

    def _require_tenant_writable(self, context: TenantContext) -> None:
        tenant = self.storage.get_by_id("tenants", context.tenant_id)
        if not tenant:
            raise PermissionError("tenant not found")
        if tenant.get("status") == "suspended":
            raise PermissionError("tenant_suspended")

    def _count(
        self,
        context: TenantContext,
        table: str,
        filters: dict[str, Any] | None = None,
        *,
        date_field: str | None = None,
        since_today: bool = False,
    ) -> int:
        return self.storage.count(
            table,
            tenant_id=context.tenant_id,
            filters=filters,
            date_field=date_field,
            since=_today_start() if since_today else None,
        )

    def _sum_tokens(self, context: TenantContext, *, since_today: bool = False, since_days: int | None = None, month_utc: bool = False) -> int:
        since = _today_start() if since_today else None
        if since_days:
            since = utc_now() - timedelta(days=since_days)
        return self.storage.sum("token_usage", "total_tokens", tenant_id=context.tenant_id, date_field="created_at", since=since, month_utc=month_utc)


def _public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in user.items() if key != "password_hash"}


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _without_secret_fields(data: dict[str, Any]) -> dict[str, Any]:
    forbidden = {"cookie", "cookies", "token", "password", "api_key", "cdp_url"}
    text = " ".join(str(key).lower() for key in data)
    if any(secret in text for secret in forbidden):
        raise ValueError("secret fields are not accepted in SaaS platform account metadata")
    return dict(data)


def _pick(data: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key in allowed}


def _is_retryable_error(error_type: Any, message: Any) -> bool:
    value = f"{error_type or ''} {message or ''}".lower()
    return any(
        marker in value
        for marker in (
            "runtime_locked",
            "temporary_cdp_unreachable",
            "cdp_unreachable",
            "runtime_not_running",
            "page.goto timeout",
            "network timeout",
            "llm timeout",
            "timeouterror",
        )
    )


def _today_start():
    now = utc_now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _keyword_summary(result: dict[str, Any]) -> dict[str, int]:
    scan = result.get("scan_summary") or {}
    plan = result.get("batch_plan_summary") or {}
    review = result.get("llm_review_summary") or {}
    return {
        "elapsed_ms": int(result.get("elapsed_ms") or 0),
        "discovered_contents": int(scan.get("scanned_contents") or scan.get("successful_content_count") or 0),
        "scanned_comments": int(scan.get("scanned_comments") or 0),
        "lead_candidates": int(scan.get("lead_candidates") or 0),
        "eligible_count": int(plan.get("eligible_count") or 0),
        "selected_count": int(plan.get("selected_count") or 0),
        "prompt_tokens": int(review.get("prompt_tokens") or 0),
        "completion_tokens": int(review.get("completion_tokens") or 0),
        "total_tokens": int(review.get("total_tokens") or 0),
    }


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception as exc:
        raise ValueError("invalid timezone") from exc


def _parse_daily_time(value: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except Exception as exc:
        raise ValueError("daily_time must use HH:MM") from exc
    if hour not in range(24) or minute not in range(60):
        raise ValueError("daily_time must use HH:MM")
    return hour, minute


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


class ServiceConflictError(RuntimeError):
    pass


def _safe_limit(limit: int) -> int:
    return min(max(int(limit), 1), 200)


def _preview_template_values() -> dict[str, str]:
    return {
        "whatsapp": "+1 555 0100",
        "email": "hello@example.com",
        "website": "https://example.com",
        "contact": "WhatsApp or email",
        "campaign_name": "Preview Campaign",
        "keyword": "preview",
        "author_name": "Preview User",
    }
