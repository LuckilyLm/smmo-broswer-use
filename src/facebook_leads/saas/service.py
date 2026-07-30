from __future__ import annotations

import secrets
import json
import re
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .auth import hash_password, needs_rehash, verify_password
from .artifacts import load_json_safe, safe_artifact_path
from .artifact_bundle import ArtifactObjectConfig, upload_execution_artifacts, write_execution_bundle
from .config import ProductionConfig
from .db import utc_now
from .logging import configure_logging, log_context
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
    "description",
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
    "target_regions_json",
    "content_types_json",
    "content_language",
}
LEAD_WRITE_FIELDS = {"status", "manual_intent_level", "assigned_user_id", "contacted_at", "invalid_reason"}
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
        self.logger = configure_logging("service", config.log_level if config else "INFO")

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
        self.logger.info("login attempt", extra={"email_domain": _email_domain(email)})
        user = self.storage.find_one("users", {"email": email.lower(), "status": "active"})
        if not user or not verify_password(password, user["password_hash"]):
            self.logger.warning("login failed", extra={"email_domain": _email_domain(email), "user_found": bool(user)})
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
        self.logger.info("login succeeded", extra={"tenant_id": membership["tenant_id"], "user_id": user["id"], "role": membership["role"]})
        return {"access_token": token, "user": _public_user(user), "tenant_id": membership["tenant_id"]}

    def logout(self, token: str) -> None:
        session = self.storage.get_by_id("sessions", token)
        self.storage.delete_by_id("sessions", token)
        if session:
            self.audit.record(action="auth.logout", resource_type="session", tenant_id=session["tenant_id"], user_id=session["user_id"])
            self.logger.info("logout completed", extra={"tenant_id": session["tenant_id"], "user_id": session["user_id"]})

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
            if account.get("login_status") == "logged_in" and account.get("connection_status") != "connected":
                self.logger.info(
                    "platform account connection status reconciled from login state",
                    extra={
                        "tenant_id": context.tenant_id,
                        "user_id": context.user_id,
                        "platform_account_id": account["id"],
                        "from_connection_status": account.get("connection_status"),
                        "login_status": account.get("login_status"),
                    },
                )
                updated = self.storage.update_by_id(
                    "platform_accounts",
                    account["id"],
                    {"connection_status": "connected", "last_checked_at": account.get("last_checked_at") or utc_now()},
                    tenant_id=context.tenant_id,
                )
                if updated:
                    account.update(updated)
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
            self.logger.warning("platform account create rejected", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform": platform, "reason": "unsupported_platform"})
            raise ValueError("unsupported platform")
        self.logger.info("platform account create started", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform": platform, "fields": sorted(payload)})
        account = self.storage.insert("platform_accounts", {**payload, "tenant_id": context.tenant_id, "config_json": {}, "connection_metadata": {}, "login_status": "unknown"})
        self.audit.record(action="platform_account.create", resource_type="platform_account", resource_id=account["id"], tenant_id=context.tenant_id, user_id=context.user_id, metadata=payload)
        self.logger.info("platform account created", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account["id"], "platform": platform})
        return account

    def update_platform_account(self, context: TenantContext, account_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        self._require_tenant_writable(context)
        account = self.storage.get_by_id("platform_accounts", account_id, tenant_id=context.tenant_id)
        if not account:
            self.logger.warning("platform account update missed", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id})
            return None
        require_permission(context, Permission.PLATFORM_ACCOUNT_WRITE)
        payload = _pick(_without_secret_fields(data), PLATFORM_ACCOUNT_WRITE_FIELDS)
        if payload.get("platform") not in {None, *PLATFORMS}:
            self.logger.warning("platform account update rejected", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id, "platform": payload.get("platform"), "reason": "unsupported_platform"})
            raise ValueError("unsupported platform")
        updated = self.storage.update_by_id("platform_accounts", account_id, payload, tenant_id=context.tenant_id)
        self.logger.info("platform account updated", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id, "fields": sorted(payload)})
        return updated

    def delete_platform_account(self, context: TenantContext, account_id: str) -> None:
        self._require_tenant_writable(context)
        self._require_platform_account(context, account_id)
        require_permission(context, Permission.PLATFORM_ACCOUNT_WRITE)
        if self.storage.find_one("campaigns", {"tenant_id": context.tenant_id, "platform_account_id": account_id, "deleted_at": None}):
            self.logger.warning("platform account delete blocked", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id, "reason": "platform_account_in_use"})
            raise ServiceConflictError("platform_account_in_use")
        runtime = self.runtime_registry.get_runtime(context, account_id)
        if runtime:
            self.logger.info("platform runtime stopping before account delete", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id, "runtime_id": runtime["id"]})
            self.runtime_registry.stop_runtime(context, account_id)
        self.storage.delete_by_id("platform_accounts", account_id, tenant_id=context.tenant_id)
        self.logger.info("platform account deleted", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id})

    def connect_platform_account(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_runtime_available()
        self._require_platform_account(context, account_id)
        require_permission(context, Permission.RUNTIME_CONTROL)
        self.logger.info("platform runtime start requested", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id})
        runtime = self.runtime_registry.start_runtime(context, account_id)
        if runtime.get("status") != "running":
            message = str(runtime.get("last_error") or "browser runtime did not start")
            self.logger.warning(
                "platform runtime start failed",
                extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id, "runtime_id": runtime.get("id"), "runtime_status": runtime.get("status"), "error": message},
            )
            raise BrowserRuntimeError("runtime_start_failed", message)
        self.storage.update_by_id(
            "platform_accounts",
            account_id,
            {"connection_status": "login_required", "login_status": "unknown", "last_connection_error": None},
            tenant_id=context.tenant_id,
        )
        self.logger.info("platform runtime started", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id, "runtime_id": runtime["id"], "runtime_status": runtime.get("status")})
        return {"runtime": safe_runtime(runtime), "connection_status": "login_required", "login_status": "unknown"}

    async def check_platform_login(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_runtime_available()
        self._require_platform_account(context, account_id)
        require_permission(context, Permission.RUNTIME_CONTROL)
        self.logger.info("platform login check requested", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id})
        return await self.runtime_registry.check_login(context, account_id)

    def reconnect_platform_account(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_runtime_available()
        self._require_platform_account(context, account_id)
        require_permission(context, Permission.RUNTIME_CONTROL)
        self.logger.info("platform runtime restart requested", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id})
        runtime = self.runtime_registry.restart_runtime(context, account_id)
        if runtime.get("status") != "running":
            message = str(runtime.get("last_error") or "browser runtime did not start")
            self.logger.warning(
                "platform runtime restart failed",
                extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id, "runtime_id": runtime.get("id"), "runtime_status": runtime.get("status"), "error": message},
            )
            raise BrowserRuntimeError("runtime_start_failed", message)
        self.storage.update_by_id(
            "platform_accounts",
            account_id,
            {"connection_status": "login_required", "login_status": "unknown", "last_connection_error": None},
            tenant_id=context.tenant_id,
        )
        self.logger.info("platform runtime restarted", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id, "runtime_id": runtime["id"], "runtime_status": runtime.get("status")})
        return {"runtime": safe_runtime(runtime), "connection_status": "login_required"}

    def stop_platform_runtime(self, context: TenantContext, account_id: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_runtime_available()
        self._require_platform_account(context, account_id)
        require_permission(context, Permission.RUNTIME_CONTROL)
        self.logger.info("platform runtime stop requested", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id})
        runtime = self.runtime_registry.stop_runtime(context, account_id)
        self.logger.info("platform runtime stopped", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "platform_account_id": account_id, "runtime": safe_runtime(runtime)})
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

    def list_campaigns(self, context: TenantContext, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        limit = _safe_limit(limit)
        self.logger.info("campaign list requested", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "limit": limit, "offset": max(offset, 0), "filters": _non_empty_keys(filters or {})})
        campaigns = self._query_campaigns(context, filters or {}, limit=limit, offset=max(offset, 0))
        self.logger.info("campaign list completed", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "count": len(campaigns), "limit": limit, "offset": max(offset, 0)})
        return self._enrich_campaigns(context, campaigns)

    def count_campaigns(self, context: TenantContext, filters: dict[str, Any] | None = None) -> int:
        return self._query_campaign_count(context, filters or {})

    def get_campaign_detail(self, context: TenantContext, campaign_id: str) -> dict[str, Any]:
        self.logger.info("campaign detail requested", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign_id})
        campaign = self._enrich_campaigns(context, [self._require_campaign(context, campaign_id)])[0]
        account = self.storage.get_by_id("platform_accounts", campaign["platform_account_id"], tenant_id=context.tenant_id)
        template_id = campaign.get("default_reply_template_id")
        return {
            "campaign": campaign,
            "platform_account": account,
            "keywords": self.list_keywords(context, campaign_id),
            "schedule": self.get_campaign_schedule(context, campaign_id),
            "default_reply_template": self.storage.get_by_id("reply_templates", template_id, tenant_id=context.tenant_id) if isinstance(template_id, str) else None,
            "matching_rules_count": self.storage.count("reply_match_rules", tenant_id=context.tenant_id, filters={"campaign_id": campaign_id, "archived_at": None}),
            "leads_count": self.storage.count("leads", tenant_id=context.tenant_id, filters={"campaign_id": campaign_id}),
            "pending_replies_count": self.storage.count("reply_candidates", tenant_id=context.tenant_id, filters={"campaign_id": campaign_id, "status": "pending_approval"}),
            "recent_executions": self.storage.list("executions", tenant_id=context.tenant_id, filters={"campaign_id": campaign_id}, limit=10),
        }

    def create_campaign(self, context: TenantContext, data: dict[str, Any]) -> dict[str, Any]:
        return self.create_campaign_with_keywords(context, data, [])

    def create_campaign_with_keywords(self, context: TenantContext, data: dict[str, Any], keywords: list[str] | None = None) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self.quota.check_quota(context.tenant_id, "campaigns")
        normalized_keywords = _normalize_keywords(keywords) if keywords else []
        if len(normalized_keywords) > 1:
            self.quota.require_feature(context.tenant_id, "allow_multi_keyword")
        payload = self._campaign_payload(context, data)
        require_permission(context, Permission.CAMPAIGN_WRITE)
        self.logger.info(
            "campaign create started",
            extra={
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "platform_account_id": payload.get("platform_account_id"),
                "keyword_count": len(normalized_keywords),
                "fields": sorted(_pick(data, CAMPAIGN_WRITE_FIELDS)),
            },
        )
        with self.storage.transaction() as session:
            campaign = self.storage.insert("campaigns", payload, session=session)
            for keyword in normalized_keywords:
                self.storage.insert(
                    "campaign_keywords",
                    {
                        "tenant_id": context.tenant_id,
                        "campaign_id": campaign["id"],
                        "keyword": keyword,
                        "enabled": True,
                        "priority": 100,
                    },
                    session=session,
                )
        self.audit.record(action="campaign.create", resource_type="campaign", resource_id=campaign["id"], tenant_id=context.tenant_id, user_id=context.user_id, metadata=_pick(data, CAMPAIGN_WRITE_FIELDS))
        self.logger.info("campaign created", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign["id"], "keyword_count": len(normalized_keywords), "status": campaign.get("status")})
        return campaign

    def _campaign_payload(self, context: TenantContext, data: dict[str, Any]) -> dict[str, Any]:
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
        if payload.get("default_reply_template_id"):
            self._require_reply_template(context, payload["default_reply_template_id"])
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
            "target_regions_json": [],
            "content_types_json": [],
            "content_language": "any",
        }
        return {**defaults, **payload, "tenant_id": context.tenant_id}

    def update_campaign(self, context: TenantContext, campaign_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        self._require_tenant_writable(context)
        if not self.storage.get_by_id("campaigns", campaign_id, tenant_id=context.tenant_id):
            self.logger.warning("campaign update missed", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign_id})
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
        if payload.get("default_reply_template_id"):
            self._require_reply_template(context, payload["default_reply_template_id"])
        updated = self.storage.update_by_id("campaigns", campaign_id, payload, tenant_id=context.tenant_id)
        self.logger.info("campaign updated", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign_id, "fields": sorted(payload), "status": updated.get("status") if updated else None})
        return updated

    def delete_campaign(self, context: TenantContext, campaign_id: str) -> None:
        self._require_tenant_writable(context)
        self._require_campaign(context, campaign_id)
        require_permission(context, Permission.CAMPAIGN_WRITE)
        active = self.storage.query_one(
            "SELECT id FROM executions WHERE tenant_id = ? AND campaign_id = ? AND status IN (?, ?) LIMIT 1",
            [context.tenant_id, campaign_id, "queued", "running"],
        )
        if active:
            self.logger.warning("campaign delete blocked", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign_id, "execution_id": active["id"], "reason": "campaign_has_active_execution"})
            raise ServiceConflictError("campaign_has_active_execution")
        self.storage.update_by_id(
            "campaigns",
            campaign_id,
            {"status": "archived", "deleted_at": utc_now()},
            tenant_id=context.tenant_id,
        )
        self.logger.info("campaign archived", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign_id})

    def list_keywords(self, context: TenantContext, campaign_id: str) -> list[dict[str, Any]]:
        self._require_campaign(context, campaign_id)
        return self.storage.list("campaign_keywords", tenant_id=context.tenant_id, filters={"campaign_id": campaign_id})

    def create_keyword(self, context: TenantContext, campaign_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_campaign(context, campaign_id)
        require_permission(context, Permission.KEYWORD_WRITE)
        keywords = _normalize_keywords([str(data.get("keyword") or "")])
        self._require_keyword_quota(context, campaign_id, keywords, enabled=bool(data.get("enabled", True)))
        row = self.storage.insert("campaign_keywords", {"enabled": True, "priority": 100, **_pick(data, KEYWORD_WRITE_FIELDS), "keyword": keywords[0], "tenant_id": context.tenant_id, "campaign_id": campaign_id})
        self.logger.info("campaign keyword created", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign_id, "keyword_id": row["id"], "enabled": row.get("enabled")})
        return row

    def create_keywords(self, context: TenantContext, campaign_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_campaign(context, campaign_id)
        require_permission(context, Permission.KEYWORD_WRITE)
        keywords = _normalize_keywords([str(item) for item in data.get("keywords", [])])
        enabled = bool(data.get("enabled", True))
        priority = int(data.get("priority") or 100)
        self._require_keyword_quota(context, campaign_id, keywords, enabled=enabled)
        rows: list[dict[str, Any]] = []
        with self.storage.transaction() as session:
            for keyword in keywords:
                rows.append(
                    self.storage.insert(
                        "campaign_keywords",
                        {
                            "tenant_id": context.tenant_id,
                            "campaign_id": campaign_id,
                            "keyword": keyword,
                            "enabled": enabled,
                            "priority": priority,
                        },
                        session=session,
                    )
                )
        self.logger.info("campaign keywords bulk created", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign_id, "created_count": len(rows), "enabled": enabled})
        return {"items": rows, "created": len(rows)}

    def update_keyword(self, context: TenantContext, keyword_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        self._require_tenant_writable(context)
        if not self.storage.get_by_id("campaign_keywords", keyword_id, tenant_id=context.tenant_id):
            return None
        require_permission(context, Permission.KEYWORD_WRITE)
        payload = _pick(data, KEYWORD_WRITE_FIELDS)
        if "keyword" in payload:
            payload["keyword"] = _normalize_keywords([str(payload["keyword"])])[0]
        return self.storage.update_by_id("campaign_keywords", keyword_id, payload, tenant_id=context.tenant_id)

    def delete_keyword(self, context: TenantContext, keyword_id: str) -> None:
        self._require_tenant_writable(context)
        if not self.storage.get_by_id("campaign_keywords", keyword_id, tenant_id=context.tenant_id):
            raise PermissionError("keyword not found")
        require_permission(context, Permission.KEYWORD_WRITE)
        self.storage.delete_by_id("campaign_keywords", keyword_id, tenant_id=context.tenant_id)

    def list_leads(self, context: TenantContext, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        limit = _safe_limit(limit)
        safe_offset = max(offset, 0)
        self.logger.info("lead list requested", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "limit": limit, "offset": safe_offset, "filters": _non_empty_keys(filters or {})})
        rows = self._query_leads(context, filters or {}, limit=limit, offset=safe_offset)
        total = self._query_lead_count(context, filters or {})
        self.logger.info("lead list completed", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "count": len(rows), "total": total, "limit": limit, "offset": safe_offset})
        return {"items": rows, "limit": limit, "offset": safe_offset, "total": total}

    def get_lead(self, context: TenantContext, lead_id: str) -> dict[str, Any] | None:
        self.logger.info("lead detail requested", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "lead_id": lead_id})
        lead = self.storage.get_by_id("leads", lead_id, tenant_id=context.tenant_id)
        if not lead:
            self.logger.warning("lead detail missed", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "lead_id": lead_id})
            return None
        campaign = self.storage.get_by_id("campaigns", lead["campaign_id"], tenant_id=context.tenant_id)
        account = self.storage.get_by_id("platform_accounts", lead["platform_account_id"], tenant_id=context.tenant_id)
        return {**lead, "campaign": campaign, "platform_account": account}

    def update_lead(self, context: TenantContext, lead_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self._require_tenant_writable(context)
        lead = self._require_lead(context, lead_id)
        require_permission(context, Permission.CAMPAIGN_WRITE)
        payload = _pick(data, LEAD_WRITE_FIELDS)
        if payload.get("assigned_user_id"):
            self._require_tenant_user(context, payload["assigned_user_id"])
        if payload.get("status"):
            self._validate_lead_transition(str(lead.get("status") or "new"), str(payload["status"]))
        if payload.get("status") == "invalid" and not (payload.get("invalid_reason") or lead.get("invalid_reason")):
            raise ValueError("invalid_reason_required")
        payload["updated_by"] = context.user_id
        updated = self.storage.update_by_id("leads", lead_id, payload, tenant_id=context.tenant_id) or lead
        self.audit.record(action="lead.update", resource_type="lead", resource_id=lead_id, tenant_id=context.tenant_id, user_id=context.user_id, metadata=payload)
        self.logger.info("lead updated", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": lead.get("campaign_id"), "lead_id": lead_id, "fields": sorted(payload), "from_status": lead.get("status"), "to_status": updated.get("status")})
        return updated

    def list_lead_notes(self, context: TenantContext, lead_id: str, *, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        self._require_lead(context, lead_id)
        safe_limit, safe_offset = _safe_limit(limit), max(offset, 0)
        filters = {"lead_id": lead_id}
        return {
            "items": self.storage.list("lead_notes", tenant_id=context.tenant_id, filters=filters, limit=safe_limit, offset=safe_offset),
            "limit": safe_limit,
            "offset": safe_offset,
            "total": self.storage.count("lead_notes", tenant_id=context.tenant_id, filters=filters),
        }

    def create_lead_note(self, context: TenantContext, lead_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self._require_lead(context, lead_id)
        require_permission(context, Permission.CAMPAIGN_WRITE)
        row = self.storage.insert(
            "lead_notes",
            {
                "tenant_id": context.tenant_id,
                "lead_id": lead_id,
                "author_user_id": context.user_id,
                "note": str(data["note"]).strip(),
                "metadata_json": data.get("metadata_json") or {},
            },
        )
        self.audit.record(action="lead.note.create", resource_type="lead", resource_id=lead_id, tenant_id=context.tenant_id, user_id=context.user_id)
        self.logger.info("lead note created", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "lead_id": lead_id, "note_id": row["id"]})
        return row

    def assign_lead(self, context: TenantContext, lead_id: str, assigned_user_id: str) -> dict[str, Any]:
        return self.update_lead(context, lead_id, {"assigned_user_id": assigned_user_id, "status": "assigned"})

    def mark_lead_contacted(self, context: TenantContext, lead_id: str) -> dict[str, Any]:
        return self.update_lead(context, lead_id, {"status": "contacted", "contacted_at": utc_now()})

    def mark_lead_invalid(self, context: TenantContext, lead_id: str, invalid_reason: str) -> dict[str, Any]:
        return self.update_lead(context, lead_id, {"status": "invalid", "invalid_reason": invalid_reason})

    def bulk_update_leads(self, context: TenantContext, lead_ids: list[str], data: dict[str, Any]) -> dict[str, Any]:
        self._require_tenant_writable(context)
        require_permission(context, Permission.CAMPAIGN_WRITE)
        payload = _pick(data, LEAD_WRITE_FIELDS)
        if payload.get("assigned_user_id"):
            self._require_tenant_user(context, payload["assigned_user_id"])
        updated: list[dict[str, Any]] = []
        with self.storage.transaction() as session:
            for lead_id in lead_ids:
                lead = self.storage.get_by_id("leads", lead_id, tenant_id=context.tenant_id, session=session)
                if not lead:
                    self.logger.warning("lead bulk update missed", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "lead_id": lead_id})
                    raise PermissionError("lead not found")
                if payload.get("status"):
                    self._validate_lead_transition(str(lead.get("status") or "new"), str(payload["status"]))
                row = self.storage.update_by_id("leads", lead_id, {**payload, "updated_by": context.user_id}, tenant_id=context.tenant_id, session=session)
                if row:
                    updated.append(row)
        self.audit.record(action="lead.bulk_update", resource_type="lead", tenant_id=context.tenant_id, user_id=context.user_id, metadata={"count": len(updated)})
        self.logger.info("lead bulk updated", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "requested": len(lead_ids), "updated": len(updated), "fields": sorted(payload)})
        return {"items": updated, "updated": len(updated)}

    def lead_timeline(self, context: TenantContext, lead_id: str) -> dict[str, Any]:
        lead = self._require_lead(context, lead_id)
        items: list[dict[str, Any]] = [
            {"type": "lead.created", "created_at": lead.get("created_at"), "title": "Lead created", "metadata": {"status": lead.get("status")}},
        ]
        if lead.get("assigned_user_id"):
            items.append({"type": "lead.assigned", "created_at": lead.get("updated_at"), "title": "Lead assigned", "metadata": {"assigned_user_id": lead.get("assigned_user_id")}})
        if lead.get("contacted_at"):
            items.append({"type": "lead.contacted", "created_at": lead.get("contacted_at"), "title": "Lead contacted", "metadata": {}})
        if lead.get("invalid_reason"):
            items.append({"type": "lead.invalid", "created_at": lead.get("updated_at"), "title": "Lead marked invalid", "metadata": {"reason": lead.get("invalid_reason")}})
        for note in self.storage.list("lead_notes", tenant_id=context.tenant_id, filters={"lead_id": lead_id}, limit=200):
            items.append({"type": "lead.note", "created_at": note.get("created_at"), "title": "Note added", "metadata": note})
        for candidate in self.storage.list("reply_candidates", tenant_id=context.tenant_id, filters={"comment_fingerprint": lead.get("comment_fingerprint")}, limit=50):
            items.append({"type": "reply_candidate." + str(candidate.get("status")), "created_at": candidate.get("created_at"), "title": "Reply candidate", "metadata": candidate})
        items.sort(key=lambda item: str(item.get("created_at") or ""))
        return {"items": items, "limit": len(items), "offset": 0, "total": len(items)}

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
        template = self._require_reply_template(context, template_id)
        require_permission(context, Permission.REPLY_RULE_WRITE)
        if template.get("is_default"):
            raise ServiceConflictError("default_reply_template_in_use")
        if self.storage.find_one("campaigns", {"tenant_id": context.tenant_id, "default_reply_template_id": template_id, "deleted_at": None}):
            raise ServiceConflictError("reply_template_in_use_by_campaign")
        if self.storage.find_one("reply_match_rules", {"tenant_id": context.tenant_id, "reply_template_id": template_id, "archived_at": None}):
            raise ServiceConflictError("reply_template_in_use_by_rule")
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
        _validate_reply_match_rule_payload(payload)
        if payload.get("campaign_id"):
            self._require_campaign(context, payload["campaign_id"])
        if payload.get("reply_template_id"):
            self._require_reply_template(context, payload["reply_template_id"])
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
        _validate_reply_match_rule_payload(merged)
        if merged.get("campaign_id"):
            self._require_campaign(context, merged["campaign_id"])
        if merged.get("reply_template_id"):
            self._require_reply_template(context, merged["reply_template_id"])
        match_comment({"text": "test", "author_name": "preview", "fingerprint": "preview"}, {}, [merged])
        return self.storage.update_by_id("reply_match_rules", rule_id, payload, tenant_id=context.tenant_id)

    def copy_reply_match_rule(self, context: TenantContext, rule_id: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        source = self.storage.get_by_id("reply_match_rules", rule_id, tenant_id=context.tenant_id)
        if not source or source.get("archived_at"):
            raise PermissionError("reply match rule not found")
        require_permission(context, Permission.REPLY_RULE_WRITE)
        payload = _pick(source, REPLY_MATCH_RULE_WRITE_FIELDS)
        payload["name"] = f"{source['name']} Copy"
        payload["enabled"] = False
        return self.create_reply_match_rule(context, payload)

    def delete_reply_match_rule(self, context: TenantContext, rule_id: str) -> None:
        self._require_tenant_writable(context)
        if not self.storage.get_by_id("reply_match_rules", rule_id, tenant_id=context.tenant_id):
            raise PermissionError("reply match rule not found")
        require_permission(context, Permission.REPLY_RULE_WRITE)
        self.storage.update_by_id("reply_match_rules", rule_id, {"enabled": False, "archived_at": utc_now()}, tenant_id=context.tenant_id)

    def test_reply_match_rule(self, context: TenantContext, data: dict[str, Any]) -> dict[str, Any]:
        campaign = self.storage.get_by_id("campaigns", data.get("campaign_id"), tenant_id=context.tenant_id) if data.get("campaign_id") else {}
        rule = {"id": "preview", "name": data.get("name") or "Preview", "enabled": True, **_pick(data, REPLY_MATCH_RULE_WRITE_FIELDS)}
        _validate_reply_match_rule_payload(rule)
        result = match_comment({"text": data.get("comment_text") or "", "author_name": data.get("author_name") or "", "fingerprint": "preview"}, campaign or {}, [rule])
        template = self._select_reply_template(context, result.template_id, campaign or {}) if result.matched else None
        status = "matched" if result.matched else "blocked" if result.blocked_reason else "not_matched"
        return {**result.__dict__, "status": status, "selected_template_id": (template or {}).get("id"), "selected_template_name": (template or {}).get("name")}

    def _with_execution_provenance(self, context: TenantContext, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        execution_ids = {row.get("execution_id") for row in rows if row.get("execution_id")}
        provenance_by_execution: dict[str, str] = {}
        for execution_id in execution_ids:
            execution = self.storage.get_by_id("executions", execution_id, tenant_id=context.tenant_id)
            snapshot = (execution or {}).get("config_snapshot") or {}
            if snapshot.get("provenance") == "demo" or snapshot.get("demo_seed") is True:
                provenance_by_execution[str(execution_id)] = "demo"
        return [
            {**row, "provenance": provenance_by_execution.get(str(row.get("execution_id")))}
            for row in rows
        ]

    def list_reply_candidates(self, context: TenantContext, filters: dict[str, Any] | None = None, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        allowed = {"campaign_id", "execution_id", "reply_plan_id", "status"}
        safe_filters = {key: value for key, value in (filters or {}).items() if key in allowed}
        rows = self.storage.list("reply_candidates", tenant_id=context.tenant_id, filters=safe_filters, limit=_safe_limit(limit), offset=offset)
        total = self.storage.count("reply_candidates", tenant_id=context.tenant_id, filters=safe_filters)
        return {"items": self._with_execution_provenance(context, rows), "limit": _safe_limit(limit), "offset": offset, "total": total}

    def approve_reply_candidate(self, context: TenantContext, candidate_id: str) -> dict[str, Any]:
        candidate = self._require_reply_candidate(context, candidate_id)
        self._require_reply_approval_role(context)
        if candidate["status"] in {"approved", "sent"}:
            self._sync_reply_plan(context, candidate.get("reply_plan_id"))
            return candidate
        if candidate["status"] not in {"pending_approval", "blocked"}:
            raise ServiceConflictError("candidate_not_approvable")
        if candidate.get("blocked_reason") or not str(candidate.get("rendered_reply_text") or "").strip():
            raise ServiceConflictError("candidate_blocked")
        row = self.storage.update_by_id("reply_candidates", candidate_id, {"status": "approved", "approved_by": context.user_id, "approved_at": utc_now(), "blocked_reason": None}, tenant_id=context.tenant_id) or candidate
        self._sync_reply_plan(context, row.get("reply_plan_id"))
        self.audit.record(action="reply_candidate.approve", resource_type="reply_candidate", resource_id=candidate_id, tenant_id=context.tenant_id, user_id=context.user_id)
        return row

    def reject_reply_candidate(self, context: TenantContext, candidate_id: str, reason: str | None = None) -> dict[str, Any]:
        candidate = self._require_reply_candidate(context, candidate_id)
        self._require_reply_approval_role(context)
        reason_text = str(reason or "").strip()
        if not reason_text:
            raise ValueError("reject_reason_required")
        if candidate["status"] not in {"pending_approval", "blocked", "approved"}:
            raise ServiceConflictError("candidate_not_rejectable")
        row = self.storage.update_by_id("reply_candidates", candidate_id, {"status": "rejected", "blocked_reason": reason_text, "rejected_by": context.user_id, "rejected_at": utc_now()}, tenant_id=context.tenant_id) or candidate
        self._sync_reply_plan(context, row.get("reply_plan_id"))
        self.audit.record(action="reply_candidate.reject", resource_type="reply_candidate", resource_id=candidate_id, tenant_id=context.tenant_id, user_id=context.user_id)
        return row

    def cancel_reply_candidate(self, context: TenantContext, candidate_id: str) -> dict[str, Any]:
        candidate = self._require_reply_candidate(context, candidate_id)
        self._require_reply_approval_role(context)
        if candidate["status"] not in {"pending_approval", "blocked", "approved"}:
            raise ServiceConflictError("candidate_not_cancellable")
        row = self.storage.update_by_id("reply_candidates", candidate_id, {"status": "cancelled", "blocked_reason": "cancelled"}, tenant_id=context.tenant_id) or candidate
        self._sync_reply_plan(context, row.get("reply_plan_id"))
        self.audit.record(action="reply_candidate.cancel", resource_type="reply_candidate", resource_id=candidate_id, tenant_id=context.tenant_id, user_id=context.user_id)
        return row

    def bulk_approve_reply_candidates(self, context: TenantContext, candidate_ids: list[str]) -> dict[str, Any]:
        items = [self.approve_reply_candidate(context, candidate_id) for candidate_id in candidate_ids]
        return {"items": items, "updated": len(items)}

    def bulk_reject_reply_candidates(self, context: TenantContext, candidate_ids: list[str], reason: str) -> dict[str, Any]:
        items = [self.reject_reply_candidate(context, candidate_id, reason) for candidate_id in candidate_ids]
        return {"items": items, "updated": len(items)}

    def update_reply_candidate_content(self, context: TenantContext, candidate_id: str, content: str) -> dict[str, Any]:
        candidate = self._require_reply_candidate(context, candidate_id)
        self._require_reply_approval_role(context)
        if not content.strip() or len(content) > 2000:
            raise ValueError("rendered_reply_invalid")
        if candidate["status"] in {"sent", "rejected", "cancelled"}:
            raise ServiceConflictError("candidate_content_locked")
        row = self.storage.update_by_id("reply_candidates", candidate_id, {"rendered_reply_text": content, "status": "pending_approval", "approved_by": None, "approved_at": None, "blocked_reason": None}, tenant_id=context.tenant_id) or candidate
        self._sync_reply_plan(context, row.get("reply_plan_id"))
        return row

    def list_reply_plans(self, context: TenantContext, filters: dict[str, Any] | None = None, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        allowed = {"campaign_id", "execution_id", "status"}
        safe_filters = {key: value for key, value in (filters or {}).items() if key in allowed}
        rows = self.storage.list("reply_plans", tenant_id=context.tenant_id, filters=safe_filters, limit=_safe_limit(limit), offset=offset)
        total = self.storage.count("reply_plans", tenant_id=context.tenant_id, filters=safe_filters)
        return {"items": self._with_execution_provenance(context, rows), "limit": _safe_limit(limit), "offset": offset, "total": total}

    def approve_reply_plan(self, context: TenantContext, plan_id: str) -> dict[str, Any]:
        plan = self._require_reply_plan(context, plan_id)
        self._require_reply_approval_role(context, automatic_allowed=True)
        plan = self._sync_reply_plan(context, plan_id) or plan
        if plan["status"] == "executed":
            return plan
        if int(plan.get("total_candidates") or 0) <= 0:
            raise ServiceConflictError("no_candidates")
        if plan["status"] not in {"approved", "pending_approval"}:
            raise ServiceConflictError("plan_not_approvable")
        if int(plan.get("approved_count") or 0) <= 0:
            raise ServiceConflictError("no_approved_candidates")
        row = self.storage.update_by_id("reply_plans", plan_id, {"status": "approved", "approved_count": plan["approved_count"], "approved_by": context.user_id, "approved_at": utc_now(), "blocked_reason": None}, tenant_id=context.tenant_id) or plan
        self.audit.record(action="reply_plan.approve", resource_type="reply_plan", resource_id=plan_id, tenant_id=context.tenant_id, user_id=context.user_id)
        return row

    def cancel_reply_plan(self, context: TenantContext, plan_id: str) -> dict[str, Any]:
        plan = self._require_reply_plan(context, plan_id)
        self._require_reply_approval_role(context, automatic_allowed=True)
        if plan["status"] not in {"pending_approval", "approved", "blocked"}:
            raise ServiceConflictError("plan_not_cancellable")
        return self.storage.update_by_id("reply_plans", plan_id, {"status": "cancelled"}, tenant_id=context.tenant_id) or plan

    def execute_reply_plan(self, context: TenantContext, plan_id: str) -> dict[str, Any]:
        plan = self._require_reply_plan(context, plan_id)
        self._require_reply_approval_role(context, automatic_allowed=True)
        plan = self._sync_reply_plan(context, plan_id) or plan
        if plan["status"] == "executed":
            return plan
        if plan["status"] != "approved":
            raise ServiceConflictError("plan_not_executable")
        approved_candidates = self.storage.list("reply_candidates", tenant_id=context.tenant_id, filters={"reply_plan_id": plan_id, "status": "approved"}, limit=1000)
        if not approved_candidates:
            self._sync_reply_plan(context, plan_id)
            raise ServiceConflictError("no_approved_candidates")
        guard = self._reply_send_guard(context, plan)
        if guard:
            for candidate in approved_candidates:
                self.storage.insert_ignore(
                    "reply_records",
                    {
                        "tenant_id": context.tenant_id,
                        "reply_candidate_id": candidate["id"],
                        "reply_plan_id": plan_id,
                        "campaign_id": plan["campaign_id"],
                        "platform_account_id": plan["platform_account_id"],
                        "comment_id": candidate.get("comment_id"),
                        "reply_text": candidate.get("rendered_reply_text") or "",
                        "status": "blocked",
                        "verified": False,
                        "error_type": guard,
                        "error_message": guard,
                        "idempotency_key": f"{candidate['id']}:blocked:{guard}",
                    },
                )
            return self.storage.update_by_id("reply_plans", plan_id, {"status": "blocked", "blocked_reason": guard}, tenant_id=context.tenant_id) or plan
        # Sending remains deliberately unavailable here. A future sender must persist and
        # verify each candidate outcome before marking the plan executed.
        raise ServiceConflictError("reply_sender_not_implemented")

    def list_reply_records(self, context: TenantContext, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return self.query_reply_records(context, {}, limit=limit, offset=offset)

    def query_reply_records(self, context: TenantContext, filters: dict[str, Any], *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        safe_limit, safe_offset = _safe_limit(limit), max(offset, 0)
        clauses = ["tenant_id = ?"]
        values: list[Any] = [context.tenant_id]
        for column in ["campaign_id", "platform_account_id", "status", "verified", "error_type"]:
            value = filters.get(column)
            if value is not None and value != "":
                clauses.append(f"{column} = ?")
                values.append(value)
        if filters.get("author_name") or filters.get("keyword"):
            subclauses: list[str] = []
            subvalues: list[Any] = [context.tenant_id]
            if filters.get("author_name"):
                subclauses.append("LOWER(COALESCE(author_name, '')) LIKE ?")
                subvalues.append(f"%{str(filters['author_name']).lower()}%")
            if filters.get("keyword"):
                subclauses.append("LOWER(COALESCE(comment_text, '')) LIKE ?")
                subvalues.append(f"%{str(filters['keyword']).lower()}%")
            candidates = self.storage.query_all(
                f"SELECT id FROM reply_candidates WHERE tenant_id = ? AND ({' OR '.join(subclauses)})",
                subvalues,
            )
            candidate_ids = [row["id"] for row in candidates]
            if not candidate_ids:
                clauses.append("1 = 0")
            else:
                clauses.append(f"reply_candidate_id IN ({', '.join('?' for _ in candidate_ids)})")
                values.extend(candidate_ids)
        if filters.get("created_from"):
            clauses.append("created_at >= ?")
            values.append(filters["created_from"])
        if filters.get("created_to"):
            clauses.append("created_at < ?")
            values.append(filters["created_to"])
        where = " AND ".join(clauses)
        total_row = self.storage.query_one(f"SELECT COUNT(*) AS count FROM reply_records WHERE {where}", values)
        rows = self.storage.query_all(
            f"SELECT * FROM reply_records WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*values, safe_limit, safe_offset],
        )
        candidate_ids = {row.get("reply_candidate_id") for row in rows if row.get("reply_candidate_id")}
        plan_ids = {row.get("reply_plan_id") for row in rows if row.get("reply_plan_id")}
        candidates = {
            candidate_id: self.storage.get_by_id("reply_candidates", candidate_id, tenant_id=context.tenant_id)
            for candidate_id in candidate_ids
        }
        plans = {
            plan_id: self.storage.get_by_id("reply_plans", plan_id, tenant_id=context.tenant_id)
            for plan_id in plan_ids
        }
        execution_rows = [
            {
                **row,
                "execution_id": (candidates.get(row.get("reply_candidate_id")) or {}).get("execution_id")
                or (plans.get(row.get("reply_plan_id")) or {}).get("execution_id"),
            }
            for row in rows
        ]
        return {"items": self._with_execution_provenance(context, execution_rows), "limit": safe_limit, "offset": safe_offset, "total": int(total_row["count"] if total_row else 0)}

    def get_reply_record_detail(self, context: TenantContext, record_id: str) -> dict[str, Any]:
        record = self.storage.get_by_id("reply_records", record_id, tenant_id=context.tenant_id)
        if not record:
            raise PermissionError("reply record not found")
        candidate_id = record.get("reply_candidate_id")
        plan_id = record.get("reply_plan_id")
        candidate = self.storage.get_by_id("reply_candidates", candidate_id, tenant_id=context.tenant_id) if isinstance(candidate_id, str) else None
        plan = self.storage.get_by_id("reply_plans", plan_id, tenant_id=context.tenant_id) if isinstance(plan_id, str) else None
        campaign = self.storage.get_by_id("campaigns", record["campaign_id"], tenant_id=context.tenant_id)
        account = self.storage.get_by_id("platform_accounts", record["platform_account_id"], tenant_id=context.tenant_id)
        execution_id = (plan or {}).get("execution_id") or (candidate or {}).get("execution_id")
        enriched_record = self._with_execution_provenance(context, [{**record, "execution_id": execution_id}])[0]
        template_id = (candidate or {}).get("reply_template_id")
        rule_id = (candidate or {}).get("matched_rule_id")
        return {
            "record": enriched_record,
            "candidate": candidate,
            "plan": plan,
            "campaign": campaign,
            "account": account,
            "execution": self.storage.get_by_id("executions", execution_id, tenant_id=context.tenant_id) if isinstance(execution_id, str) else None,
            "original_comment": {"comment_id": record.get("comment_id"), "text": (candidate or {}).get("comment_text")},
            "matched_rule": self.storage.get_by_id("reply_match_rules", rule_id, tenant_id=context.tenant_id) if isinstance(rule_id, str) else None,
            "template": self.storage.get_by_id("reply_templates", template_id, tenant_id=context.tenant_id) if isinstance(template_id, str) else None,
        }

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
        return self._sync_reply_plan(context, plan["id"]) or plan

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

    def retry_execution(self, context: TenantContext, execution_id: str) -> dict[str, Any]:
        self._require_tenant_writable(context)
        execution = self._require_execution(context, execution_id)
        require_permission(context, Permission.EXECUTION_RUN)
        retryable = execution.get("status") in {"failed", "cancelled"} or _is_retryable_error(execution.get("error_type"), execution.get("error_message"))
        if execution.get("status") in {"queued", "running", "completed"} or not retryable:
            raise ServiceConflictError("execution_not_retryable")
        result = self.enqueue_campaign_execution(context, execution["campaign_id"], trigger_type="retry")
        self.audit.record(action="execution.retry", resource_type="execution", resource_id=execution_id, tenant_id=context.tenant_id, user_id=context.user_id, metadata={"retry_execution_id": result["execution_id"]})
        return result

    def execution_timeline(self, context: TenantContext, execution_id: str) -> dict[str, Any]:
        execution = self._require_execution(context, execution_id)
        items = [{"type": f"execution.{execution.get('status')}", "created_at": execution.get("created_at"), "title": "Execution created", "metadata": execution}]
        queue = self.storage.find_one("execution_queue_items", {"tenant_id": context.tenant_id, "execution_id": execution_id})
        if queue:
            items.append({"type": f"queue.{queue.get('status')}", "created_at": queue.get("queued_at"), "title": "Queue item", "metadata": queue})
        for keyword in self.list_execution_keywords(context, execution_id):
            items.append({"type": f"keyword.{keyword.get('status')}", "created_at": keyword.get("created_at"), "title": "Keyword execution", "metadata": keyword})
        items.sort(key=lambda row: str(row.get("created_at") or ""))
        return {"items": items, "limit": len(items), "offset": 0, "total": len(items)}

    def execution_artifacts(self, context: TenantContext, execution_id: str, *, artifact_type: str | None = None) -> dict[str, Any]:
        self._require_execution(context, execution_id)
        root = safe_artifact_path(self.artifacts_root, "tenants", context.tenant_id, "executions", execution_id)
        items: list[dict[str, Any]] = []
        manifest_by_path = self._artifact_manifest_by_path(root)
        if root.exists():
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                kind = _artifact_type(path)
                if artifact_type and kind != artifact_type:
                    continue
                rel = path.relative_to(root).as_posix()
                if artifact_type is None and rel != "execution_report.html":
                    continue
                items.append(
                    {
                        "type": kind,
                        "name": path.name,
                        "url": f"/api/executions/{execution_id}/artifacts/{rel}",
                        "external_url": manifest_by_path.get(rel, {}).get("url"),
                        "created_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                    }
                )
        items.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        return {"items": items, "limit": len(items), "offset": 0, "total": len(items)}

    def execution_artifact_path(self, context: TenantContext, execution_id: str, artifact_path: str) -> Path:
        self._require_execution(context, execution_id)
        parts = [part for part in str(artifact_path).replace("\\", "/").split("/") if part]
        root = safe_artifact_path(self.artifacts_root, "tenants", context.tenant_id, "executions", execution_id)
        target = safe_artifact_path(root, *parts)
        if not target.is_file():
            raise FileNotFoundError(artifact_path)
        return target

    def _artifact_manifest_by_path(self, root: Path) -> dict[str, dict[str, Any]]:
        manifest = load_json_safe(root / "artifact_manifest.json", default={})
        items = manifest.get("items") if isinstance(manifest, dict) else None
        if not isinstance(items, list):
            return {}
        output: dict[str, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            name = str(item.get("name") or "")
            for path in root.rglob(name):
                if path.is_file():
                    output[path.relative_to(root).as_posix()] = item
        return output

    def execution_logs(self, context: TenantContext, execution_id: str, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        self._require_execution(context, execution_id)
        root = safe_artifact_path(self.artifacts_root, "tenants", context.tenant_id, "executions", execution_id)
        lines: list[dict[str, Any]] = []
        if root.exists():
            for path in root.rglob("*"):
                if not path.is_file() or _artifact_type(path) != "log":
                    continue
                target = path.resolve()
                if root not in target.parents:
                    continue
                try:
                    for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
                        lines.append({"source": target.name, "line": _redact_sensitive(line)[:2000]})
                except OSError:
                    continue
        safe_limit, safe_offset = _safe_limit(limit), max(offset, 0)
        return {"items": lines[safe_offset : safe_offset + safe_limit], "limit": safe_limit, "offset": safe_offset, "total": len(lines)}

    def execution_token_usage(self, context: TenantContext, execution_id: str, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        self._require_execution(context, execution_id)
        safe_limit, safe_offset = _safe_limit(limit), max(offset, 0)
        filters = {"execution_id": execution_id}
        return {
            "items": self.storage.list("token_usage", tenant_id=context.tenant_id, filters=filters, limit=safe_limit, offset=safe_offset),
            "limit": safe_limit,
            "offset": safe_offset,
            "total": self.storage.count("token_usage", tenant_id=context.tenant_id, filters=filters),
        }

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

    def dashboard_summary(self, context: TenantContext, *, range_days: int = 7) -> dict[str, Any]:
        queue_counts = self.storage.queue_counts(tenant_id=context.tenant_id)
        since = utc_now() - timedelta(days=max(1, min(range_days, 30)) - 1)
        lead_trend = self.storage.query_all(
            """
            SELECT DATE(created_at) AS date, COUNT(*) AS leads, 0 AS comments_scanned
            FROM leads
            WHERE tenant_id = ? AND created_at >= ?
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at)
            """,
            [context.tenant_id, since],
        )
        comment_trend = {
            str(row["date"]): int(row["comments_scanned"])
            for row in self.storage.query_all(
                """
                SELECT DATE(created_at) AS date, COALESCE(SUM(scanned_comments), 0) AS comments_scanned
                FROM executions
                WHERE tenant_id = ? AND created_at >= ?
                GROUP BY DATE(created_at)
                """,
                [context.tenant_id, since],
            )
        }
        for row in lead_trend:
            row["leads"] = int(row["leads"])
            row["comments_scanned"] = comment_trend.get(str(row["date"]), 0)
        intent_distribution = self.storage.query_all(
            """
            SELECT COALESCE(manual_intent_level, final_intent_level, 'unknown') AS intent_level, COUNT(*) AS count
            FROM leads
            WHERE tenant_id = ?
            GROUP BY COALESCE(manual_intent_level, final_intent_level, 'unknown')
            """,
            [context.tenant_id],
        )
        for row in intent_distribution:
            row["count"] = int(row["count"])
        campaign_performance = [
            {
                "campaign_id": row["id"],
                "campaign_name": row["name"],
                "platform": row.get("platform") or "facebook",
                "status": row["status"],
                "lead_count": row.get("lead_count") or 0,
                "pending_reply_count": row.get("pending_reply_count") or 0,
                "last_execution_at": row.get("last_execution_at"),
            }
            for row in self.list_campaigns(context, {}, limit=10)
        ]
        pending_reply_items = self.list_reply_candidates(context, {"status": "pending_approval"}, limit=10)["items"]
        platform_status = [
            {
                "account_id": account["id"],
                "platform": account["platform"],
                "display_name": account["display_name"],
                "connection_status": account["connection_status"],
                "login_status": account.get("login_status"),
                "runtime_status": (account.get("runtime") or {}).get("status") if account.get("runtime") else None,
            }
            for account in self.list_platform_accounts(context)
        ]
        comments_today = self.storage.query_one(
            "SELECT COALESCE(SUM(scanned_comments), 0) AS count FROM executions WHERE tenant_id = ? AND created_at >= ?",
            [context.tenant_id, _today_start()],
        )
        return {
            "active_campaigns": self._count(context, "campaigns", {"status": "active"}),
            "connected_platform_accounts": self._count(context, "platform_accounts", {"connection_status": "connected"}),
            "comments_scanned_today": int(comments_today["count"] if comments_today else 0),
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
            "failed_tasks_today": self._count(context, "executions", {"status": "failed"}, date_field="created_at", since_today=True),
            "reply_success_rate": self._reply_success_rate(context),
            "system_send_enabled": self._system_send_enabled(),
            "reply_safety_message": "" if self._system_send_enabled() else "回复发送当前处于关闭状态",
            "lead_trend": lead_trend,
            "intent_distribution": intent_distribution,
            "campaign_performance": campaign_performance,
            "recent_executions": self.list_executions(context, limit=5),
            "pending_reply_items": pending_reply_items,
            "platform_status": platform_status,
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

    def repair_terminal_execution_queue_items(self) -> int:
        terminal_statuses = {"completed", "partial", "failed", "cancelled"}
        running_items = self.storage.list(
            "execution_queue_items",
            filters={"status": "running"},
            limit=10000,
        )
        repaired = 0
        for queue_item in running_items:
            execution = self.storage.get_by_id(
                "executions",
                queue_item["execution_id"],
                tenant_id=queue_item["tenant_id"],
            )
            if not execution or execution.get("status") not in terminal_statuses:
                continue
            status = "completed" if execution["status"] in {"completed", "partial"} else execution["status"]
            self.storage.update_by_id(
                "execution_queue_items",
                queue_item["id"],
                {"status": status, "finished_at": execution.get("finished_at") or utc_now()},
                tenant_id=queue_item["tenant_id"],
            )
            repaired += 1
        return repaired

    async def run_campaign(self, context: TenantContext, campaign_id: str) -> dict[str, Any]:
        self.logger.info("manual campaign run requested", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign_id})
        execution = self.enqueue_campaign_execution(context, campaign_id, trigger_type="manual")
        return {"execution_id": execution["id"], "status": "queued", "send_disabled": True}

    def enqueue_campaign_execution(self, context: TenantContext, campaign_id: str, *, trigger_type: str, schedule_trigger_key: str | None = None) -> dict[str, Any]:
        self._require_tenant_writable(context)
        self.logger.info("campaign enqueue started", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign_id, "trigger_type": trigger_type, "has_schedule_trigger_key": bool(schedule_trigger_key)})
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
            self.logger.warning("campaign enqueue rejected", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign_id, "queued_count": queued_count, "limit": self.max_queued_executions_per_tenant, "reason": "queue_limit_reached"})
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
            self.logger.warning("campaign enqueue rejected", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign_id, "reason": "no_enabled_keyword"})
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
            self.logger.warning("campaign enqueue deduplicated", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign_id, "execution_id": execution["id"]})
            raise ValueError("schedule window already enqueued")
        self.logger.info("campaign enqueued", extra={"tenant_id": context.tenant_id, "user_id": context.user_id, "campaign_id": campaign_id, "execution_id": execution["id"], "queue_item_id": queue["id"], "keyword_count": len(keywords), "send_disabled": True})
        return execution

    async def run_queue_item(self, queue_item: dict[str, Any]) -> dict[str, Any]:
        context = TenantContext(tenant_id=queue_item["tenant_id"], user_id="worker", role="worker")
        execution = self._require_execution(context, queue_item["execution_id"])
        campaign = self._require_campaign(context, queue_item["campaign_id"])
        run_logger = log_context(self.logger, tenant_id=context.tenant_id, campaign_id=campaign["id"], execution_id=execution["id"], queue_item_id=queue_item["id"])
        run_logger.info("queue item run started", extra={"attempt_count": queue_item.get("attempt_count"), "status": queue_item.get("status")})
        snapshot = execution.get("config_snapshot") or {}
        execution_campaign = {**campaign, **{key: value for key, value in snapshot.items() if key != "keywords"}}
        if execution_campaign.get("llm_enabled") and self.config and not (
            self.config.llm_endpoint and self.config.llm_api_key and self.config.llm_model
        ):
            run_logger.warning("queue item failed preflight", extra={"reason": "llm_configuration_missing"})
            return self._finish_queue_failure(
                queue_item,
                execution,
                "llm_configuration_missing",
                "LLM endpoint, API key, and model must be configured",
            )
        account = self.storage.get_by_id("platform_accounts", snapshot.get("platform_account_id") or campaign["platform_account_id"], tenant_id=context.tenant_id)
        if not account:
            run_logger.warning("queue item failed preflight", extra={"reason": "platform_account_not_found"})
            return self._finish_queue_failure(queue_item, execution, "platform_account_not_connected", "platform account not found")
        if account.get("login_status") != "logged_in":
            try:
                login = await self.runtime_registry.check_login(context, account["id"])
                account = self.storage.get_by_id("platform_accounts", account["id"], tenant_id=context.tenant_id) or account
                run_logger.info("queue item refreshed platform login", extra={"platform_account_id": account["id"], "login_status": login.get("login_status"), "connection_status": login.get("connection_status")})
            except Exception as exc:
                run_logger.warning("queue item login refresh failed", extra={"platform_account_id": account["id"], "error_type": type(exc).__name__})
        try:
            runtime = self._preflight_runtime(context, account, campaign["id"], create_failed_execution=False)
        except ValueError as exc:
            run_logger.warning("queue item runtime preflight failed", extra={"error_type": str(exc), "platform_account_id": account.get("id")})
            return self._finish_queue_error(queue_item, execution, str(exc), str(exc))
        lock_key = runtime["id"]
        if lock_key in self._runtime_locks:
            run_logger.warning("queue item runtime lock busy", extra={"runtime_id": runtime["id"], "lock_scope": "process"})
            return self._retry_queue_item(queue_item, execution, "runtime_locked", "same platform account already has an active run")
        provider = self.providers.get(account["platform"])
        if not provider:
            run_logger.warning("queue item provider missing", extra={"platform": account["platform"]})
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
            run_logger.warning("queue item has empty keyword snapshot")
            return self._finish_queue_failure(queue_item, execution, "no_enabled_keyword", "campaign has no enabled keyword")
        database_lock = self.storage.acquire_runtime_lock(lock_key)
        if database_lock is None:
            run_logger.warning("queue item runtime lock busy", extra={"runtime_id": runtime["id"], "lock_scope": "database"})
            return self._retry_queue_item(queue_item, execution, "runtime_locked", "same browser runtime is already in use by another worker")
        if lock_key in self._runtime_locks:
            self.storage.release_runtime_lock(database_lock)
            run_logger.warning("queue item runtime lock busy", extra={"runtime_id": runtime["id"], "lock_scope": "process_after_db_lock"})
            return self._retry_queue_item(queue_item, execution, "runtime_locked", "same platform account already has an active run")
        self._runtime_locks.add(lock_key)
        self.storage.update_by_id("executions", execution["id"], {"status": "running", "stage": "worker", "started_at": utc_now(), "total_keywords": len(keywords), "progress_percent": 0}, tenant_id=context.tenant_id)
        run_logger.info("queue item execution marked running", extra={"runtime_id": runtime["id"], "platform_account_id": account["id"], "keyword_count": len(keywords), "send_disabled": True})
        try:
            completed = 0
            failed = 0
            retryable_failures = 0
            last_retryable_error = ("temporary_error", "temporary provider failure")
            for index, keyword in enumerate(keywords, start=1):
                current = self.storage.get_by_id("executions", execution["id"], tenant_id=context.tenant_id) or execution
                if current.get("cancel_requested"):
                    run_logger.info("queue item cancellation observed", extra={"completed": completed, "failed": failed, "keyword_index": index})
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
                run_logger.info("keyword run started", extra={"execution_keyword_id": keyword_row["id"], "keyword_index": index, "keyword_total": len(keywords)})
                try:
                    result = await provider.run_campaign(self._provider_request(context, execution_campaign, keyword["keyword"], run_context, execution["id"]))
                    summary = _keyword_summary(result)
                    status = "failed" if result.get("status") in {"failed", "not_implemented"} or result.get("error_type") else "completed"
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
                    run_logger.info("keyword run finished", extra={"execution_keyword_id": keyword_row["id"], "keyword_index": index, "status": status, **summary, "error_type": result.get("error_type")})
                except Exception as exc:
                    failed += 1
                    if _is_retryable_error(type(exc).__name__, str(exc)):
                        retryable_failures += 1
                        last_retryable_error = (type(exc).__name__, str(exc))
                    self.storage.update_by_id("execution_keywords", keyword_row["id"], {"status": "failed", "finished_at": utc_now(), "error_type": type(exc).__name__, "error_message": str(exc)}, tenant_id=context.tenant_id)
                    run_logger.exception("keyword run crashed", extra={"execution_keyword_id": keyword_row["id"], "keyword_index": index, "error_type": type(exc).__name__})
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
                run_logger.warning("queue item all failures retryable", extra={"failed": failed, "retryable_failures": retryable_failures, "error_type": last_retryable_error[0]})
                return self._retry_queue_item(queue_item, execution, *last_retryable_error)
            final_execution = self.storage.get_by_id("executions", execution["id"], tenant_id=context.tenant_id) or execution
            status = "cancelled" if final_execution.get("cancel_requested") else ("completed" if completed == len(keywords) else "partial" if completed else "failed")
            self._update_execution_aggregate(context, execution["id"], total=len(keywords), completed=completed, failed=failed, status=status, finished=True)
            final_execution = self._finalize_execution_artifacts(context, execution["id"])
            if status in {"completed", "partial"}:
                self.generate_reply_plan_for_execution(context, execution["id"])
            run_logger.info("queue item run finished", extra={"status": status, "completed": completed, "failed": failed, "keyword_count": len(keywords), "execution_report": bool(final_execution)})
            return self.storage.update_by_id("execution_queue_items", queue_item["id"], {"status": "completed" if status in {"completed", "partial"} else status, "finished_at": utc_now()}, tenant_id=context.tenant_id) or queue_item
        except Exception as exc:
            self.storage.update_by_id("browser_runtimes", runtime["id"], {"status": "unhealthy", "last_error": "campaign run failed"}, tenant_id=context.tenant_id)
            run_logger.exception("queue item run crashed", extra={"runtime_id": runtime["id"], "error_type": type(exc).__name__})
            return self._finish_queue_error(queue_item, execution, type(exc).__name__, str(exc))
        finally:
            self._runtime_locks.discard(lock_key)
            self.storage.release_runtime_lock(database_lock)
            run_logger.info("queue item runtime lock released", extra={"runtime_id": runtime["id"]})

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
            custom_positive_keywords=tuple(str(item).strip() for item in (campaign.get("positive_keywords_json") or []) if str(item).strip()),
            history_path=str(execution_root / "reply_history.jsonl"),
            runs_root=str(execution_root / "runs"),
            run_context=run_context,
        )

    def _finalize_execution_artifacts(self, context: TenantContext, execution_id: str) -> dict[str, Any] | None:
        execution = self.storage.get_by_id("executions", execution_id, tenant_id=context.tenant_id)
        if not execution:
            return None
        root = safe_artifact_path(self.artifacts_root, "tenants", context.tenant_id, "executions", execution_id)
        keywords = self.storage.list("execution_keywords", tenant_id=context.tenant_id, filters={"execution_id": execution_id}, limit=1000)
        leads = self.storage.list("leads", tenant_id=context.tenant_id, filters={"campaign_id": execution["campaign_id"]}, limit=200)
        campaign = self.storage.get_by_id("campaigns", execution["campaign_id"], tenant_id=context.tenant_id)
        if campaign:
            execution = {**execution, "campaign_name": campaign.get("name")}
            account = self.storage.get_by_id("platform_accounts", campaign["platform_account_id"], tenant_id=context.tenant_id)
            if account:
                execution["platform_account_name"] = account.get("display_name")
        paths = write_execution_bundle(root, tenant_id=context.tenant_id, execution=execution, keywords=keywords, leads=leads)
        upload = upload_execution_artifacts(root, tenant_id=context.tenant_id, execution_id=execution_id, config=self._artifact_object_config())
        metadata = {
            "execution_report_json": str(paths["execution_report_json"]),
            "execution_report_html": str(paths["execution_report_html"]),
            "object_storage": {
                "enabled": bool(upload.get("enabled")),
                "uploaded": upload.get("uploaded"),
                "error": upload.get("error"),
                "items": [
                    item
                    for item in upload.get("items", [])
                    if item.get("name") == "execution_report.html"
                ],
            },
        }
        self.logger.info("execution artifacts finalized", extra={"tenant_id": context.tenant_id, "execution_id": execution_id, "uploaded": upload.get("uploaded"), "object_storage_enabled": upload.get("enabled"), "object_storage_error": upload.get("error")})
        return self.storage.update_by_id("executions", execution_id, {"config_snapshot": {**(execution.get("config_snapshot") or {}), "artifacts": metadata}}, tenant_id=context.tenant_id) or execution

    def _artifact_object_config(self) -> ArtifactObjectConfig:
        config = self.config
        return ArtifactObjectConfig(
            enabled=bool(config and config.artifact_s3_enabled),
            endpoint=config.artifact_s3_endpoint if config else None,
            access_key=config.artifact_s3_access_key if config else None,
            secret_key=config.artifact_s3_secret_key if config else None,
            bucket=config.artifact_s3_bucket if config else None,
            region=config.artifact_s3_region if config else "us-east-1",
            prefix=config.artifact_s3_prefix if config else "saas-artifacts",
            public_base_url=config.artifact_s3_public_base_url if config else None,
            secure=bool(config.artifact_s3_secure) if config else True,
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
        log_context(self.logger, tenant_id=execution["tenant_id"], campaign_id=execution.get("campaign_id"), execution_id=execution["id"], queue_item_id=queue_item["id"]).warning("queue item scheduled for retry", extra={"attempt_count": attempts, "max_attempts": max_attempts, "delay_seconds": delay, "error_type": error_type})
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
            context = TenantContext(tenant_id=execution["tenant_id"], user_id="worker", role="worker")
            try:
                updated = self._finalize_execution_artifacts(context, execution["id"]) or updated
            except Exception as exc:
                self.logger.warning(
                    "failed execution artifact finalization failed",
                    extra={
                        "tenant_id": execution["tenant_id"],
                        "campaign_id": execution.get("campaign_id"),
                        "execution_id": execution["id"],
                        "error_type": type(exc).__name__,
                    },
                )
            self.notifications.execution_finished(updated)
        log_context(self.logger, tenant_id=execution["tenant_id"], campaign_id=execution.get("campaign_id"), execution_id=execution["id"], queue_item_id=queue_item["id"]).error("queue item failed", extra={"error_type": error_type})
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

    def _query_campaigns(self, context: TenantContext, filters: dict[str, Any], *, limit: int, offset: int) -> list[dict[str, Any]]:
        clauses, values = self._campaign_filter_clauses(context, filters)
        return self.storage.query_all(
            f"SELECT * FROM campaigns WHERE {' AND '.join(clauses)} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            [*values, limit, offset],
        )

    def _query_campaign_count(self, context: TenantContext, filters: dict[str, Any]) -> int:
        clauses, values = self._campaign_filter_clauses(context, filters)
        row = self.storage.query_one(f"SELECT COUNT(*) AS count FROM campaigns WHERE {' AND '.join(clauses)}", values)
        return int(row["count"] if row else 0)

    def _campaign_filter_clauses(self, context: TenantContext, filters: dict[str, Any]) -> tuple[list[str], list[Any]]:
        clauses = ["tenant_id = ?", "deleted_at IS NULL"]
        values: list[Any] = [context.tenant_id]
        for column in ["status", "platform_account_id", "reply_mode"]:
            value = filters.get(column)
            if value:
                clauses.append(f"{column} = ?")
                values.append(value)
        if filters.get("platform"):
            account_ids = [
                row["id"]
                for row in self.storage.list(
                    "platform_accounts",
                    tenant_id=context.tenant_id,
                    filters={"platform": filters["platform"]},
                    limit=1000,
                )
            ]
            if not account_ids:
                clauses.append("1 = 0")
            else:
                placeholders = ", ".join("?" for _ in account_ids)
                clauses.append(f"platform_account_id IN ({placeholders})")
                values.extend(account_ids)
        if filters.get("search"):
            clauses.append("(LOWER(name) LIKE ? OR LOWER(COALESCE(description, '')) LIKE ?)")
            search = f"%{str(filters['search']).lower()}%"
            values.extend([search, search])
        if filters.get("created_from"):
            clauses.append("created_at >= ?")
            values.append(filters["created_from"])
        if filters.get("created_to"):
            clauses.append("created_at < ?")
            values.append(filters["created_to"])
        return clauses, values

    def _enrich_campaigns(self, context: TenantContext, campaigns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for campaign in campaigns:
            campaign_id = campaign["id"]
            account = self.storage.get_by_id("platform_accounts", campaign["platform_account_id"], tenant_id=context.tenant_id)
            schedule = self.storage.find_one("campaign_schedules", {"tenant_id": context.tenant_id, "campaign_id": campaign_id})
            last_execution = self.storage.query_one(
                "SELECT * FROM executions WHERE tenant_id = ? AND campaign_id = ? ORDER BY created_at DESC LIMIT 1",
                [context.tenant_id, campaign_id],
            )
            campaign["platform"] = account.get("platform") if account else None
            campaign["platform_account_name"] = account.get("display_name") if account else None
            campaign["keyword_count"] = self.storage.count("campaign_keywords", tenant_id=context.tenant_id, filters={"campaign_id": campaign_id})
            campaign["lead_count"] = self.storage.count("leads", tenant_id=context.tenant_id, filters={"campaign_id": campaign_id})
            campaign["pending_reply_count"] = self.storage.count("reply_candidates", tenant_id=context.tenant_id, filters={"campaign_id": campaign_id, "status": "pending_approval"})
            campaign["last_execution_at"] = last_execution.get("started_at") if last_execution else None
            campaign["next_run_at"] = schedule.get("next_run_at") if schedule else None
            campaign["owner_name"] = None
            campaign["schedule"] = schedule
        return campaigns

    def _query_leads(self, context: TenantContext, filters: dict[str, Any], *, limit: int, offset: int) -> list[dict[str, Any]]:
        clauses, values = self._lead_filter_clauses(context, filters)
        rows = self.storage.query_all(
            f"SELECT * FROM leads WHERE {' AND '.join(clauses)} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            [*values, limit, offset],
        )
        return [self._normalize_lead_row(row) for row in rows]

    def _normalize_lead_row(self, row: dict[str, Any]) -> dict[str, Any]:
        keywords = row.get("matched_search_keywords")
        if isinstance(keywords, str):
            try:
                parsed = json.loads(keywords)
            except json.JSONDecodeError:
                parsed = []
            row = {**row, "matched_search_keywords": parsed if isinstance(parsed, list) else []}
        return row

    def _query_lead_count(self, context: TenantContext, filters: dict[str, Any]) -> int:
        clauses, values = self._lead_filter_clauses(context, filters)
        row = self.storage.query_one(f"SELECT COUNT(*) AS count FROM leads WHERE {' AND '.join(clauses)}", values)
        return int(row["count"] if row else 0)

    def _lead_filter_clauses(self, context: TenantContext, filters: dict[str, Any]) -> tuple[list[str], list[Any]]:
        clauses = ["tenant_id = ?"]
        values: list[Any] = [context.tenant_id]
        exact = {
            "campaign_id": "campaign_id",
            "platform": "platform",
            "status": "status",
            "rule_intent_level": "rule_intent_level",
            "final_intent_level": "final_intent_level",
            "manual_intent_level": "manual_intent_level",
            "assigned_user_id": "assigned_user_id",
            "reply_allowed": "reply_allowed",
        }
        if filters.get("intent_level") and not filters.get("final_intent_level"):
            filters = {**filters, "final_intent_level": filters["intent_level"]}
        for key, column in exact.items():
            value = filters.get(key)
            if value is not None and value != "":
                clauses.append(f"{column} = ?")
                values.append(value)
        for key, column in [("created_from", "created_at"), ("created_to", "created_at")]:
            value = filters.get(key)
            if value:
                clauses.append(f"{column} {'>=' if key.endswith('from') else '<'} ?")
                values.append(value)
        search = filters.get("search") or filters.get("keyword")
        if search:
            like = f"%{str(search).lower()}%"
            clauses.append("(LOWER(COALESCE(comment_text, '')) LIKE ? OR LOWER(COALESCE(author_name, '')) LIKE ?)")
            values.extend([like, like])
        return clauses, values

    def _require_lead(self, context: TenantContext, lead_id: str) -> dict[str, Any]:
        lead = self.storage.get_by_id("leads", lead_id, tenant_id=context.tenant_id)
        if not lead:
            raise PermissionError("lead not found")
        return lead

    def _require_tenant_user(self, context: TenantContext, user_id: str) -> dict[str, Any]:
        membership = self.storage.find_one("tenant_users", {"tenant_id": context.tenant_id, "user_id": user_id})
        user = self.storage.get_by_id("users", user_id)
        if not membership or not user or user.get("status") != "active":
            raise PermissionError("user not found")
        return user

    def _validate_lead_transition(self, current: str, target: str) -> None:
        if current == target:
            return
        allowed = {
            "new": {"open", "assigned", "contacted", "qualified", "invalid", "archived"},
            "open": {"assigned", "contacted", "qualified", "invalid", "archived"},
            "assigned": {"open", "contacted", "qualified", "invalid", "archived"},
            "contacted": {"qualified", "invalid", "archived"},
            "qualified": {"contacted", "archived"},
            "invalid": {"archived"},
            "archived": set(),
        }
        if target not in allowed.get(current, set()):
            raise ServiceConflictError("invalid_lead_status_transition")

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

    def _require_reply_template(self, context: TenantContext, template_id: str) -> dict[str, Any]:
        template = self.storage.get_by_id("reply_templates", template_id, tenant_id=context.tenant_id)
        if not template or template.get("archived_at"):
            raise PermissionError("reply template not found")
        return template

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

    def _sync_reply_plan(self, context: TenantContext, plan_id: str | None) -> dict[str, Any] | None:
        if not plan_id:
            return None
        plan = self.storage.get_by_id("reply_plans", plan_id, tenant_id=context.tenant_id)
        if not plan:
            return None
        candidates = self.storage.list("reply_candidates", tenant_id=context.tenant_id, filters={"reply_plan_id": plan_id}, limit=1000)
        total = len(candidates)
        approved = sum(1 for candidate in candidates if candidate.get("status") == "approved")
        sent = sum(1 for candidate in candidates if candidate.get("status") == "sent")
        failed = sum(1 for candidate in candidates if candidate.get("status") == "failed")
        payload: dict[str, Any] = {"total_candidates": total, "approved_count": approved, "sent_count": sent, "failed_count": failed}
        if total == 0:
            payload.update({"status": "blocked", "blocked_reason": "no_candidates", "approved_by": None, "approved_at": None})
        elif plan.get("status") not in {"executed", "cancelled"}:
            if approved == 0:
                payload.update({"status": "pending_approval", "blocked_reason": None, "approved_by": None, "approved_at": None})
            elif plan.get("approved_by") or plan.get("reply_mode") == "automatic":
                payload.update({"status": "approved", "blocked_reason": None})
            else:
                payload.update({"status": "pending_approval", "blocked_reason": None})
        return self.storage.update_by_id("reply_plans", plan_id, payload, tenant_id=context.tenant_id) or plan

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

    def _require_keyword_quota(self, context: TenantContext, campaign_id: str, keywords: list[str], *, enabled: bool) -> None:
        if not enabled:
            return
        active_count = self.storage.count("campaign_keywords", tenant_id=context.tenant_id, filters={"campaign_id": campaign_id, "enabled": True})
        if active_count + len(keywords) > 1:
            self.quota.require_feature(context.tenant_id, "allow_multi_keyword")

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


def _email_domain(email: str) -> str:
    _, separator, domain = str(email or "").lower().partition("@")
    return domain if separator and domain else "unknown"


def _non_empty_keys(values: dict[str, Any]) -> list[str]:
    return sorted(key for key, value in values.items() if value is not None and value != "")


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


def _normalize_keywords(keywords: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in keywords:
        keyword = str(value or "").strip()
        if not keyword:
            continue
        if len(keyword) > 255:
            raise ValueError("keyword_too_long")
        key = keyword.casefold()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(keyword)
    if not normalized:
        raise ValueError("keyword_required")
    if len(normalized) > 50:
        raise ValueError("too_many_keywords")
    return normalized


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


def _artifact_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return "screenshot"
    if suffix in {".log", ".txt", ".jsonl"}:
        return "log"
    return "file"


def _redact_sensitive(text: str) -> str:
    patterns = [
        (r"(?i)(cookie|authorization|x-csrf-token|access[_-]?token|refresh[_-]?token|password)\s*[:=]\s*[^,\s;]+", r"\1=[REDACTED]"),
        (r"(?i)(Bearer)\s+[A-Za-z0-9._~+/=-]+", r"\1 [REDACTED]"),
        (r"(?i)(c_user|xs|fr|datr)=[^;\s]+", r"\1=[REDACTED]"),
    ]
    redacted = text
    for pattern, replacement in patterns:
        redacted = re.sub(pattern, replacement, redacted)
    return redacted


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


def _validate_reply_match_rule_payload(payload: dict[str, Any]) -> None:
    pattern = str(payload.get("regex_pattern") or "").strip()
    if pattern:
        if len(pattern) > 500:
            raise ValueError("regex_too_long")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError("invalid_regex") from exc
    minimum = payload.get("minimum_length")
    maximum = payload.get("maximum_length")
    if minimum is not None and maximum is not None and int(minimum) > int(maximum):
        raise ValueError("invalid_length_range")
