from __future__ import annotations

import hashlib
import logging
import secrets
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, insert, select, update

from .auth import hash_password
from .db import TABLES, utc_now
from .models import TenantContext


LOGGER = logging.getLogger(__name__)
ROLES = {"owner", "admin", "member", "viewer"}
MANAGE_ROLES = {"owner", "admin"}
LIMIT_FIELDS = (
    "max_users",
    "max_platform_accounts",
    "max_campaigns",
    "max_monthly_executions",
    "max_monthly_tokens",
    "max_monthly_leads",
)

PLAN_DEFINITIONS: dict[str, dict[str, Any]] = {
    "free": {
        "name": "Free",
        "description": "For evaluation and small workspaces.",
        "max_users": 2,
        "max_platform_accounts": 1,
        "max_campaigns": 2,
        "max_monthly_executions": 50,
        "max_monthly_tokens": 500_000,
        "max_monthly_leads": 500,
        "allow_scheduler": False,
        "allow_multi_keyword": False,
        "allow_advanced_reports": False,
    },
    "starter": {
        "name": "Starter",
        "description": "For small teams running regular lead discovery.",
        "max_users": 5,
        "max_platform_accounts": 3,
        "max_campaigns": 10,
        "max_monthly_executions": 500,
        "max_monthly_tokens": 5_000_000,
        "max_monthly_leads": 5_000,
        "allow_scheduler": True,
        "allow_multi_keyword": True,
        "allow_advanced_reports": False,
    },
    "pro": {
        "name": "Pro",
        "description": "For established teams with higher automation volume.",
        "max_users": 20,
        "max_platform_accounts": 10,
        "max_campaigns": 50,
        "max_monthly_executions": 5_000,
        "max_monthly_tokens": 50_000_000,
        "max_monthly_leads": 50_000,
        "allow_scheduler": True,
        "allow_multi_keyword": True,
        "allow_advanced_reports": True,
    },
    "enterprise": {
        "name": "Enterprise",
        "description": "Custom limits managed by the system administrator.",
        **{field: None for field in LIMIT_FIELDS},
        "allow_scheduler": True,
        "allow_multi_keyword": True,
        "allow_advanced_reports": True,
    },
    "legacy": {
        "name": "Legacy",
        "description": "Compatibility plan for tenants created before productization.",
        **{field: None for field in LIMIT_FIELDS},
        "allow_scheduler": True,
        "allow_multi_keyword": True,
        "allow_advanced_reports": True,
    },
}


class QuotaExceededError(Exception):
    def __init__(self, resource: str, limit: int, used: int) -> None:
        super().__init__(f"{resource} quota reached")
        self.resource = resource
        self.limit = limit
        self.used = used


class FeatureNotAvailableError(Exception):
    def __init__(self, feature: str) -> None:
        super().__init__(f"{feature} is not available on the current plan")
        self.feature = feature


def seed_plans(storage: Any) -> dict[str, dict[str, Any]]:
    seeded: dict[str, dict[str, Any]] = {}
    for code, definition in PLAN_DEFINITIONS.items():
        existing = storage.find_one("plans", {"code": code})
        payload = {"code": code, "status": "active", **definition}
        seeded[code] = storage.update_by_id("plans", existing["id"], payload) if existing else storage.insert("plans", payload)
    return seeded


def backfill_legacy_subscriptions(storage: Any) -> int:
    plans = seed_plans(storage)
    created = 0
    for tenant in storage.list("tenants", limit=100_000):
        if storage.find_one("tenant_subscriptions", {"tenant_id": tenant["id"]}):
            continue
        start, end = natural_month_period()
        storage.insert(
            "tenant_subscriptions",
            {
                "tenant_id": tenant["id"],
                "plan_id": plans["legacy"]["id"],
                "status": "active",
                "started_at": utc_now(),
                "current_period_start": start,
                "current_period_end": end,
                "overrides_json": {},
            },
        )
        created += 1
    return created


def natural_month_period(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or utc_now()
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    days = monthrange(now.year, now.month)[1]
    return start, start + timedelta(days=days)


class TenantUsageService:
    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def subscription(self, tenant_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        subscription = self.storage.find_one("tenant_subscriptions", {"tenant_id": tenant_id})
        if not subscription:
            backfill_legacy_subscriptions(self.storage)
            subscription = self.storage.find_one("tenant_subscriptions", {"tenant_id": tenant_id})
        if not subscription:
            raise RuntimeError("tenant subscription unavailable")
        plan = self.storage.get_by_id("plans", subscription["plan_id"])
        if not plan:
            raise RuntimeError("subscription plan unavailable")
        return subscription, plan

    def period(self, subscription: dict[str, Any]) -> tuple[datetime, datetime]:
        start = _datetime(subscription.get("current_period_start"))
        end = _datetime(subscription.get("current_period_end"))
        return (start, end) if start and end else natural_month_period()

    def get_usage(self, tenant_id: str) -> dict[str, int]:
        subscription, _plan = self.subscription(tenant_id)
        start, end = self.period(subscription)
        return {
            "users": self.storage.count("tenant_users", tenant_id=tenant_id),
            "platform_accounts": self.storage.count("platform_accounts", tenant_id=tenant_id),
            "campaigns": self._active_campaigns(tenant_id),
            "monthly_executions": self._aggregate("executions", "count", tenant_id, start, end),
            "monthly_tokens": self._aggregate("token_usage", "total_tokens", tenant_id, start, end),
            "monthly_leads": self._aggregate("leads", "count", tenant_id, start, end),
        }

    def _active_campaigns(self, tenant_id: str) -> int:
        table = TABLES["campaigns"]
        statement = select(func.count()).select_from(table).where(and_(table.c.tenant_id == tenant_id, table.c.deleted_at.is_(None)))
        with self.storage.session_factory() as session:
            return int(session.execute(statement).scalar_one())

    def _aggregate(self, table_name: str, value: str, tenant_id: str, start: datetime, end: datetime) -> int:
        table = TABLES[table_name]
        expression = func.count() if value == "count" else func.coalesce(func.sum(table.c[value]), 0)
        statement = select(expression).where(
            and_(table.c.tenant_id == tenant_id, table.c.created_at >= start, table.c.created_at < end)
        )
        with self.storage.session_factory() as session:
            return int(session.execute(statement).scalar_one() or 0)


class QuotaService:
    RESOURCE_LIMITS = {
        "users": "max_users",
        "platform_accounts": "max_platform_accounts",
        "campaigns": "max_campaigns",
        "monthly_executions": "max_monthly_executions",
        "monthly_tokens": "max_monthly_tokens",
        "monthly_leads": "max_monthly_leads",
    }

    def __init__(self, storage: Any, notifications: "NotificationService | None" = None) -> None:
        self.storage = storage
        self.usage_service = TenantUsageService(storage)
        self.notifications = notifications

    def get_limits(self, tenant_id: str) -> dict[str, int | None]:
        subscription, plan = self.usage_service.subscription(tenant_id)
        overrides = subscription.get("overrides_json") or {}
        return {
            resource: overrides.get(limit_field, plan.get(limit_field))
            for resource, limit_field in self.RESOURCE_LIMITS.items()
        }

    def get_usage(self, tenant_id: str) -> dict[str, int]:
        return self.usage_service.get_usage(tenant_id)

    def get_remaining(self, tenant_id: str) -> dict[str, int | None]:
        usage, limits = self.get_usage(tenant_id), self.get_limits(tenant_id)
        remaining: dict[str, int | None] = {}
        for resource, limit in limits.items():
            remaining[resource] = None if limit is None else max(int(limit) - usage[resource], 0)
        return remaining

    def summary(self, tenant_id: str) -> dict[str, Any]:
        subscription, plan = self.usage_service.subscription(tenant_id)
        usage = self.get_usage(tenant_id)
        limits = self.get_limits(tenant_id)
        return {
            "plan": _public_plan(plan),
            "subscription": subscription,
            "usage": usage,
            "limits": limits,
            "remaining": self.get_remaining(tenant_id),
        }

    def check_quota(self, tenant_id: str, resource: str, *, increment: int = 1) -> None:
        if resource not in self.RESOURCE_LIMITS:
            raise ValueError(f"unsupported quota resource: {resource}")
        used = self.get_usage(tenant_id)[resource]
        limit = self.get_limits(tenant_id)[resource]
        if limit is None:
            self._notify_usage(tenant_id, resource, used, limit)
            return
        checked_limit = int(limit)
        exceeded = used >= checked_limit if increment == 0 else used + increment > checked_limit
        if exceeded:
            self._notify_threshold(tenant_id, resource, used, checked_limit, 100)
            raise QuotaExceededError(resource, checked_limit, used)
        self._notify_usage(tenant_id, resource, used, limit)

    def require_feature(self, tenant_id: str, feature: str) -> None:
        _subscription, plan = self.usage_service.subscription(tenant_id)
        if not bool(plan.get(feature)):
            raise FeatureNotAvailableError(feature)

    def warn_all(self, tenant_id: str) -> None:
        usage, limits = self.get_usage(tenant_id), self.get_limits(tenant_id)
        for resource, used in usage.items():
            self._notify_usage(tenant_id, resource, used, limits[resource])

    def _notify_usage(self, tenant_id: str, resource: str, used: int, limit: int | None) -> None:
        if not self.notifications or limit in (None, 0):
            return
        percent = used * 100 / int(limit)
        for threshold in (100, 90, 80):
            if percent >= threshold:
                self._notify_threshold(tenant_id, resource, used, int(limit), threshold)
                break

    def _notify_threshold(self, tenant_id: str, resource: str, used: int, limit: int, threshold: int) -> None:
        if not self.notifications:
            return
        subscription, _plan = self.usage_service.subscription(tenant_id)
        start, _end = self.usage_service.period(subscription)
        self.notifications.create(
            tenant_id=tenant_id,
            notification_type="quota_exceeded" if threshold == 100 else "quota_warning",
            severity="error" if threshold == 100 else "warning",
            title="Quota reached" if threshold == 100 else "Quota warning",
            message=f"{resource.replace('_', ' ').title()}: {used} of {limit} used.",
            resource_type="quota",
            resource_id=resource,
            dedupe_key=f"quota:{start.date()}:{resource}:{threshold}",
        )


class AuditService:
    BLOCKED_KEYS = {
        "password", "new_password", "current_password", "authorization", "cookie",
        "session", "session_token", "api_key", "secret", "token", "cdp_url", "profile_path",
    }

    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        tenant_id: str | None = None,
        user_id: str | None = None,
        resource_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            return self.storage.insert(
                "audit_logs",
                {
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "action": action,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "metadata_json": self.sanitize(metadata or {}),
                },
            )
        except Exception:
            LOGGER.exception("audit record failed", extra={"action": action, "resource_type": resource_type})
            return None

    @classmethod
    def sanitize(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if key.lower() in cls.BLOCKED_KEYS else cls.sanitize(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls.sanitize(item) for item in value]
        return value


class NotificationService:
    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def create(
        self,
        *,
        tenant_id: str,
        notification_type: str,
        severity: str,
        title: str,
        message: str,
        user_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        dedupe_key: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            payload = {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "type": notification_type,
                "severity": severity,
                "title": title,
                "message": message,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "dedupe_key": dedupe_key,
            }
            return self.storage.insert_ignore("notifications", payload) if dedupe_key else self.storage.insert("notifications", payload)
        except Exception:
            LOGGER.exception("notification creation failed", extra={"tenant_id": tenant_id, "type": notification_type})
            return None

    def execution_finished(self, execution: dict[str, Any]) -> None:
        status = str(execution.get("status") or "failed")
        notification_type = {
            "completed": "execution_completed",
            "partial": "execution_partial",
        }.get(status, "execution_failed")
        try:
            self.create(
                tenant_id=execution["tenant_id"],
                notification_type=notification_type,
                severity="success" if status == "completed" else "warning" if status == "partial" else "error",
                title=f"Execution {status}",
                message=f"Campaign execution finished with status {status}.",
                resource_type="execution",
                resource_id=execution["id"],
                dedupe_key=f"execution:{execution['id']}:{status}",
            )
        except Exception:
            LOGGER.exception("execution notification failed", extra={"execution_id": execution.get("id")})


class TenantAdminService:
    def __init__(self, service: Any) -> None:
        self.service = service
        self.storage = service.storage

    def list_members(self, context: TenantContext, *, limit: int, offset: int) -> dict[str, Any]:
        self._require_manager(context)
        rows = self.storage.query_all(
            """
            SELECT tu.id, tu.tenant_id, tu.user_id, tu.role, tu.created_at, tu.updated_at,
                   u.email, u.display_name, u.status
            FROM tenant_users tu JOIN users u ON u.id = tu.user_id
            WHERE tu.tenant_id = ?
            ORDER BY tu.created_at
            LIMIT ? OFFSET ?
            """,
            [context.tenant_id, limit, offset],
        )
        return {"items": rows, "limit": limit, "offset": offset, "total": self.storage.count("tenant_users", tenant_id=context.tenant_id)}

    def add_member(self, context: TenantContext, *, email: str, role: str) -> dict[str, Any]:
        self._require_writable(context)
        self._validate_managed_role(context, role)
        self.service.quota.check_quota(context.tenant_id, "users")
        user = self.storage.find_one("users", {"email": email.lower()})
        if not user:
            raise ValueError("user_not_found")
        if self.storage.find_one("tenant_users", {"tenant_id": context.tenant_id, "user_id": user["id"]}):
            raise ValueError("member_already_exists")
        membership = self.service.add_user_to_tenant(context.tenant_id, user["id"], role=role)
        self.service.audit.record(action="member.add", resource_type="membership", resource_id=membership["id"], tenant_id=context.tenant_id, user_id=context.user_id, metadata={"role": role, "email": email})
        return membership

    def update_member(self, context: TenantContext, membership_id: str, role: str) -> dict[str, Any]:
        self._require_writable(context)
        membership = self._membership(context, membership_id)
        self._validate_change(context, membership, role)
        with self.storage.transaction() as session:
            if membership["role"] == "owner" and role != "owner":
                self._ensure_other_owner(context.tenant_id, membership_id, session=session)
            updated = self.storage.update_by_id("tenant_users", membership_id, {"role": role}, tenant_id=context.tenant_id, session=session)
        self.service.audit.record(action="member.role_change", resource_type="membership", resource_id=membership_id, tenant_id=context.tenant_id, user_id=context.user_id, metadata={"from": membership["role"], "to": role})
        return updated

    def remove_member(self, context: TenantContext, membership_id: str) -> None:
        self._require_writable(context)
        membership = self._membership(context, membership_id)
        if membership["role"] == "owner":
            if context.role != "owner":
                raise PermissionError("only owner can remove an owner")
            self._ensure_other_owner(context.tenant_id, membership_id)
        elif context.role == "admin" and membership["role"] == "admin":
            raise PermissionError("admin cannot remove admin")
        self.storage.delete_by_id("tenant_users", membership_id, tenant_id=context.tenant_id)
        self.service.audit.record(action="member.remove", resource_type="membership", resource_id=membership_id, tenant_id=context.tenant_id, user_id=context.user_id, metadata={"role": membership["role"]})

    def transfer_ownership(self, context: TenantContext, target_user_id: str) -> dict[str, Any]:
        self._require_writable(context)
        if context.role != "owner":
            raise PermissionError("owner role required")
        current = self.storage.find_one("tenant_users", {"tenant_id": context.tenant_id, "user_id": context.user_id})
        target = self.storage.find_one("tenant_users", {"tenant_id": context.tenant_id, "user_id": target_user_id})
        if not current or not target or target["id"] == current["id"]:
            raise ValueError("invalid ownership target")
        with self.storage.transaction() as session:
            self.storage.update_by_id("tenant_users", target["id"], {"role": "owner"}, tenant_id=context.tenant_id, session=session)
            self.storage.update_by_id("tenant_users", current["id"], {"role": "admin"}, tenant_id=context.tenant_id, session=session)
        self.service.audit.record(action="owner.transfer", resource_type="tenant", resource_id=context.tenant_id, tenant_id=context.tenant_id, user_id=context.user_id, metadata={"target_user_id": target_user_id})
        return {"tenant_id": context.tenant_id, "previous_owner_user_id": context.user_id, "owner_user_id": target_user_id}

    def create_invitation(self, context: TenantContext, *, email: str, role: str, expires_days: int = 7) -> dict[str, Any]:
        self._require_writable(context)
        self._validate_managed_role(context, role)
        self.service.quota.check_quota(context.tenant_id, "users")
        existing = self.storage.find_one("tenant_invitations", {"tenant_id": context.tenant_id, "email": email.lower(), "status": "pending"})
        if existing:
            raise ValueError("pending_invitation_exists")
        raw_token = secrets.token_urlsafe(32)
        invitation = self.storage.insert(
            "tenant_invitations",
            {
                "tenant_id": context.tenant_id,
                "email": email.lower(),
                "role": role,
                "token_hash": _token_hash(raw_token),
                "status": "pending",
                "expires_at": utc_now() + timedelta(days=expires_days),
                "invited_by_user_id": context.user_id,
            },
        )
        self.service.audit.record(action="member.invite", resource_type="invitation", resource_id=invitation["id"], tenant_id=context.tenant_id, user_id=context.user_id, metadata={"email": email, "role": role})
        return {**{key: value for key, value in invitation.items() if key != "token_hash"}, "token": raw_token}

    def list_invitations(self, context: TenantContext, *, limit: int, offset: int) -> dict[str, Any]:
        self._require_manager(context)
        items = self.storage.list("tenant_invitations", tenant_id=context.tenant_id, limit=limit, offset=offset)
        return {
            "items": [{key: value for key, value in item.items() if key != "token_hash"} for item in items],
            "limit": limit,
            "offset": offset,
            "total": self.storage.count("tenant_invitations", tenant_id=context.tenant_id),
        }

    def revoke_invitation(self, context: TenantContext, invitation_id: str) -> None:
        self._require_writable(context)
        invitation = self.storage.get_by_id("tenant_invitations", invitation_id, tenant_id=context.tenant_id)
        if not invitation:
            raise PermissionError("invitation not found")
        self.storage.update_by_id("tenant_invitations", invitation_id, {"status": "revoked"}, tenant_id=context.tenant_id)
        self.service.audit.record(action="member.invite_revoke", resource_type="invitation", resource_id=invitation_id, tenant_id=context.tenant_id, user_id=context.user_id)

    def accept_invitation(
        self,
        raw_token: str,
        *,
        authenticated_user_id: str | None = None,
        email: str | None = None,
        password: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        invitation = self.storage.find_one("tenant_invitations", {"token_hash": _token_hash(raw_token)})
        if not invitation or invitation["status"] != "pending":
            raise ValueError("invitation_invalid")
        expires_at = _datetime(invitation["expires_at"])
        if expires_at is None or expires_at <= utc_now():
            self.storage.update_by_id("tenant_invitations", invitation["id"], {"status": "expired"})
            raise ValueError("invitation_expired")
        user = self.storage.get_by_id("users", authenticated_user_id) if authenticated_user_id else None
        if user and user["email"].lower() != invitation["email"].lower():
            raise PermissionError("invitation email mismatch")
        if not user:
            user = self.storage.find_one("users", {"email": invitation["email"].lower()})
        if user and not authenticated_user_id:
            raise PermissionError("login required to accept invitation")
        if not user:
            if not password or len(password) < 8 or not display_name:
                raise ValueError("password and display_name are required")
            if email and email.lower() != invitation["email"].lower():
                raise PermissionError("invitation email mismatch")
            user = self.storage.insert("users", {"email": invitation["email"], "password_hash": hash_password(password), "display_name": display_name, "status": "active", "must_change_password": False, "is_system_admin": False})
        with self.storage.transaction() as session:
            existing = self.storage.find_one("tenant_users", {"tenant_id": invitation["tenant_id"], "user_id": user["id"]})
            if not existing:
                membership = self.storage.insert("tenant_users", {"tenant_id": invitation["tenant_id"], "user_id": user["id"], "role": invitation["role"]}, session=session)
            else:
                membership = existing
            self.storage.update_by_id("tenant_invitations", invitation["id"], {"status": "accepted", "accepted_by_user_id": user["id"]}, session=session)
        self.service.audit.record(action="member.invite_accept", resource_type="invitation", resource_id=invitation["id"], tenant_id=invitation["tenant_id"], user_id=user["id"])
        self.service.notifications.create(tenant_id=invitation["tenant_id"], notification_type="invitation_accepted", severity="success", title="Invitation accepted", message=f"{user['display_name']} joined the workspace.", resource_type="membership", resource_id=membership["id"])
        return {"membership": membership, "user": {"id": user["id"], "email": user["email"], "display_name": user["display_name"]}}

    def update_settings(self, context: TenantContext, data: dict[str, Any]) -> dict[str, Any]:
        self._require_writable(context)
        allowed = {
            "name",
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
        updated = self.storage.update_by_id("tenants", context.tenant_id, {key: value for key, value in data.items() if key in allowed})
        self.service.audit.record(action="tenant.settings_update", resource_type="tenant", resource_id=context.tenant_id, tenant_id=context.tenant_id, user_id=context.user_id, metadata=data)
        return updated

    def _membership(self, context: TenantContext, membership_id: str) -> dict[str, Any]:
        membership = self.storage.get_by_id("tenant_users", membership_id, tenant_id=context.tenant_id)
        if not membership:
            raise PermissionError("membership not found")
        return membership

    def _require_manager(self, context: TenantContext) -> None:
        if context.role not in MANAGE_ROLES:
            raise PermissionError("owner or admin role required")

    def _require_writable(self, context: TenantContext) -> None:
        self._require_manager(context)
        self.service._require_tenant_writable(context)

    def _validate_managed_role(self, context: TenantContext, role: str) -> None:
        if role not in ROLES or role == "owner":
            raise ValueError("invalid managed role")
        if context.role == "admin" and role == "admin":
            raise PermissionError("admin cannot manage admin")

    def _validate_change(self, context: TenantContext, membership: dict[str, Any], role: str) -> None:
        if role not in ROLES:
            raise ValueError("invalid role")
        if context.role != "owner" and (membership["role"] in {"owner", "admin"} or role in {"owner", "admin"}):
            raise PermissionError("admin can only manage member and viewer roles")
        if role == "owner":
            raise ValueError("use ownership transfer")

    def _ensure_other_owner(self, tenant_id: str, membership_id: str, *, session: Any | None = None) -> None:
        table = TABLES["tenant_users"]
        statement = select(func.count()).select_from(table).where(and_(table.c.tenant_id == tenant_id, table.c.role == "owner", table.c.id != membership_id))
        if session is not None:
            count = int(session.execute(statement).scalar_one())
        else:
            with self.storage.session_factory() as owned:
                count = int(owned.execute(statement).scalar_one())
        if count == 0:
            raise ValueError("last_owner_protected")


class SystemAdminService:
    def __init__(self, service: Any) -> None:
        self.service = service
        self.storage = service.storage

    def require(self, user_id: str) -> dict[str, Any]:
        user = self.storage.get_by_id("users", user_id)
        if not user or not user.get("is_system_admin"):
            raise PermissionError("system administrator required")
        return user

    def list_tenants(self, user_id: str, *, limit: int, offset: int) -> dict[str, Any]:
        self.require(user_id)
        items = []
        for tenant in self.storage.list("tenants", limit=limit, offset=offset):
            summary = self.service.quota.summary(tenant["id"])
            items.append({**tenant, "plan": summary["plan"], "usage": summary["usage"]})
        return {"items": items, "limit": limit, "offset": offset, "total": self.storage.count("tenants")}

    def tenant_detail(self, user_id: str, tenant_id: str) -> dict[str, Any]:
        self.require(user_id)
        tenant = self.storage.get_by_id("tenants", tenant_id)
        if not tenant:
            raise ValueError("tenant_not_found")
        summary = self.service.quota.summary(tenant_id)
        last_execution = self.storage.find_one("executions", {"tenant_id": tenant_id}, order_by=["created_at"])
        return {**tenant, **summary, "last_execution": last_execution}

    def update_subscription(self, user_id: str, tenant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self.require(user_id)
        subscription, current_plan = self.service.quota.usage_service.subscription(tenant_id)
        plan = self.storage.get_by_id("plans", data.get("plan_id")) if data.get("plan_id") else self.storage.find_one("plans", {"code": data.get("plan_code")}) if data.get("plan_code") else current_plan
        if not plan:
            raise ValueError("plan_not_found")
        allowed = {"status", "current_period_start", "current_period_end", "overrides_json"}
        updated = self.storage.update_by_id("tenant_subscriptions", subscription["id"], {"plan_id": plan["id"], **{key: value for key, value in data.items() if key in allowed}})
        if "tenant_status" in data:
            self.storage.update_by_id("tenants", tenant_id, {"status": data["tenant_status"]})
        self.service.audit.record(action="admin.subscription_update", resource_type="subscription", resource_id=subscription["id"], tenant_id=tenant_id, user_id=user_id, metadata=data)
        return updated

    def create_plan(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self.require(user_id)
        plan = self.storage.insert("plans", data)
        self.service.audit.record(action="admin.plan_create", resource_type="plan", resource_id=plan["id"], user_id=user_id, metadata=data)
        return plan

    def update_plan(self, user_id: str, plan_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self.require(user_id)
        plan = self.storage.update_by_id("plans", plan_id, data)
        if not plan:
            raise ValueError("plan_not_found")
        self.service.audit.record(action="admin.plan_update", resource_type="plan", resource_id=plan_id, user_id=user_id, metadata=data)
        return plan

    def system_usage(self, user_id: str) -> dict[str, Any]:
        self.require(user_id)
        return {
            "tenants": self.storage.count("tenants"),
            "users": self.storage.count("users"),
            "executions": self.storage.count("executions"),
            "tokens": self.storage.sum("token_usage", "total_tokens"),
            "worker_health": self.storage.count("worker_heartbeats", filters={"status": "online"}),
        }


def bootstrap_system_admin(storage: Any, email: str | None) -> bool:
    if not email:
        return False
    user = storage.find_one("users", {"email": email.lower()})
    if not user or user.get("is_system_admin"):
        return False
    storage.update_by_id("users", user["id"], {"is_system_admin": True})
    return True


def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def _public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key not in {"created_at", "updated_at"}}
