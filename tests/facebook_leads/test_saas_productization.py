from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from src.facebook_leads.saas.api import create_app
from src.facebook_leads.saas.config import ProductionConfig
from src.facebook_leads.saas.db import utc_now
from src.facebook_leads.saas.models import TenantContext
from src.facebook_leads.saas.productization import (
    AuditService,
    FeatureNotAvailableError,
    QuotaExceededError,
    backfill_legacy_subscriptions,
    seed_plans,
)
from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage


@pytest.fixture
def product(tmp_path):
    storage = SaaSStorage(tmp_path / "product.sqlite")
    service = SaaSService(storage, artifacts_root=tmp_path / "artifacts")
    tenant = service.create_tenant("Tenant A", "tenant-a", plan_code="pro")
    owner = service.create_user("owner@example.com", "pass123456", "Owner")
    admin = service.create_user("admin@example.com", "pass123456", "Admin")
    member = service.create_user("member@example.com", "pass123456", "Member")
    viewer = service.create_user("viewer@example.com", "pass123456", "Viewer")
    memberships = {
        "owner": service.add_user_to_tenant(tenant["id"], owner["id"], role="owner"),
        "admin": service.add_user_to_tenant(tenant["id"], admin["id"], role="admin"),
        "member": service.add_user_to_tenant(tenant["id"], member["id"], role="member"),
        "viewer": service.add_user_to_tenant(tenant["id"], viewer["id"], role="viewer"),
    }
    contexts = {
        role: TenantContext(tenant_id=tenant["id"], user_id=user["id"], role=role)
        for role, user in (("owner", owner), ("admin", admin), ("member", member), ("viewer", viewer))
    }
    return service, tenant, {"owner": owner, "admin": admin, "member": member, "viewer": viewer}, memberships, contexts


def test_plan_seed_and_legacy_backfill_are_idempotent(tmp_path):
    storage = SaaSStorage(tmp_path / "seed.sqlite")
    tenant = storage.insert("tenants", {"name": "Legacy", "slug": "legacy", "status": "active"})
    assert set(seed_plans(storage)) == {"free", "starter", "pro", "enterprise", "legacy"}
    assert backfill_legacy_subscriptions(storage) == 1
    assert backfill_legacy_subscriptions(storage) == 0
    subscription = storage.find_one("tenant_subscriptions", {"tenant_id": tenant["id"]})
    assert storage.get_by_id("plans", subscription["plan_id"])["code"] == "legacy"


def test_quota_enforces_limits_overrides_and_unlimited(product):
    service, tenant, _users, _memberships, _contexts = product
    subscription, _plan = service.quota.usage_service.subscription(tenant["id"])
    free = service.storage.find_one("plans", {"code": "free"})
    service.storage.update_by_id("tenant_subscriptions", subscription["id"], {"plan_id": free["id"], "overrides_json": {"max_users": 4}})
    with pytest.raises(QuotaExceededError) as error:
        service.quota.check_quota(tenant["id"], "users")
    assert (error.value.resource, error.value.limit, error.value.used) == ("users", 4, 4)
    service.storage.update_by_id("tenant_subscriptions", subscription["id"], {"overrides_json": {"max_users": None}})
    service.quota.check_quota(tenant["id"], "users", increment=0)


def test_plan_feature_flags(product):
    service, tenant, _users, _memberships, _contexts = product
    subscription, _plan = service.quota.usage_service.subscription(tenant["id"])
    free = service.storage.find_one("plans", {"code": "free"})
    service.storage.update_by_id("tenant_subscriptions", subscription["id"], {"plan_id": free["id"]})
    with pytest.raises(FeatureNotAvailableError):
        service.quota.require_feature(tenant["id"], "allow_scheduler")


def test_resource_quotas_cover_platform_campaign_execution_and_tokens(product):
    service, tenant, _users, _memberships, _contexts = product
    account = service.storage.insert("platform_accounts", {"tenant_id": tenant["id"], "platform": "facebook", "display_name": "Page", "config_json": {}, "connection_metadata": {}})
    campaign = service.storage.insert("campaigns", {"tenant_id": tenant["id"], "name": "Campaign", "platform_account_id": account["id"], "status": "active", "target_policy": "discovery_only"})
    execution = service.storage.insert("executions", {"tenant_id": tenant["id"], "campaign_id": campaign["id"], "platform": "facebook", "status": "completed", "send_disabled": True})
    service.storage.insert("token_usage", {"tenant_id": tenant["id"], "campaign_id": campaign["id"], "execution_id": execution["id"], "provider": "openai", "total_tokens": 10})
    subscription, _plan = service.quota.usage_service.subscription(tenant["id"])
    service.storage.update_by_id("tenant_subscriptions", subscription["id"], {"overrides_json": {
        "max_platform_accounts": 1,
        "max_campaigns": 1,
        "max_monthly_executions": 1,
        "max_monthly_tokens": 10,
    }})
    for resource in ("platform_accounts", "campaigns", "monthly_executions"):
        with pytest.raises(QuotaExceededError):
            service.quota.check_quota(tenant["id"], resource)
    with pytest.raises(QuotaExceededError):
        service.quota.check_quota(tenant["id"], "monthly_tokens", increment=0)


def test_owner_and_admin_member_rules(product):
    service, _tenant, users, memberships, contexts = product
    service.tenant_admin.update_member(contexts["admin"], memberships["member"]["id"], "viewer")
    with pytest.raises(PermissionError):
        service.tenant_admin.remove_member(contexts["admin"], memberships["owner"]["id"])
    with pytest.raises(PermissionError):
        service.tenant_admin.update_member(contexts["viewer"], memberships["member"]["id"], "viewer")
    transfer = service.tenant_admin.transfer_ownership(contexts["owner"], users["admin"]["id"])
    assert transfer["owner_user_id"] == users["admin"]["id"]
    assert service.storage.get_by_id("tenant_users", memberships["owner"]["id"])["role"] == "admin"
    assert service.storage.get_by_id("tenant_users", memberships["admin"]["id"])["role"] == "owner"


def test_last_owner_is_protected(product):
    service, tenant, _users, memberships, contexts = product
    service.storage.update_by_id("tenant_users", memberships["admin"]["id"], {"role": "member"})
    with pytest.raises(ValueError, match="last_owner_protected"):
        service.tenant_admin.remove_member(contexts["owner"], memberships["owner"]["id"])
    assert service.storage.count("tenant_users", tenant_id=tenant["id"], filters={"role": "owner"}) == 1


def test_invitation_hash_accept_existing_and_duplicate(product):
    service, tenant, users, _memberships, contexts = product
    existing = service.create_user("invitee@example.com", "pass123456", "Invitee")
    invitation = service.tenant_admin.create_invitation(contexts["owner"], email=existing["email"], role="member")
    stored = service.storage.get_by_id("tenant_invitations", invitation["id"])
    assert "token_hash" not in invitation
    assert stored["token_hash"] != invitation["token"]
    accepted = service.tenant_admin.accept_invitation(invitation["token"], authenticated_user_id=existing["id"])
    assert accepted["membership"]["tenant_id"] == tenant["id"]
    with pytest.raises(ValueError, match="invitation_invalid"):
        service.tenant_admin.accept_invitation(invitation["token"], authenticated_user_id=users["owner"]["id"])


def test_invitation_accept_new_expired_and_revoked(product):
    service, _tenant, _users, _memberships, contexts = product
    invitation = service.tenant_admin.create_invitation(contexts["owner"], email="new@example.com", role="viewer")
    accepted = service.tenant_admin.accept_invitation(invitation["token"], email="new@example.com", password="pass123456", display_name="New User")
    assert accepted["user"]["email"] == "new@example.com"

    expired = service.tenant_admin.create_invitation(contexts["owner"], email="expired@example.com", role="member")
    service.storage.update_by_id("tenant_invitations", expired["id"], {"expires_at": utc_now() - timedelta(days=1)})
    with pytest.raises(ValueError, match="invitation_expired"):
        service.tenant_admin.accept_invitation(expired["token"], email="expired@example.com", password="pass123456", display_name="Expired")

    revoked = service.tenant_admin.create_invitation(contexts["owner"], email="revoked@example.com", role="member")
    service.tenant_admin.revoke_invitation(contexts["owner"], revoked["id"])
    with pytest.raises(ValueError, match="invitation_invalid"):
        service.tenant_admin.accept_invitation(revoked["token"], email="revoked@example.com", password="pass123456", display_name="Revoked")


def test_audit_redacts_sensitive_metadata_and_is_tenant_scoped(product):
    service, tenant, users, _memberships, _contexts = product
    row = service.audit.record(
        tenant_id=tenant["id"],
        user_id=users["owner"]["id"],
        action="test",
        resource_type="tenant",
        metadata={"password": "secret", "nested": {"api_key": "key"}, "safe": "value"},
    )
    assert row["metadata_json"] == {"password": "[REDACTED]", "nested": {"api_key": "[REDACTED]"}, "safe": "value"}
    other = service.create_tenant("Tenant B", "tenant-b")
    service.audit.record(tenant_id=other["id"], action="other", resource_type="tenant")
    assert service.storage.count("audit_logs", tenant_id=tenant["id"]) == 1


def test_notifications_read_isolation_and_quota_dedupe(product):
    service, tenant, _users, _memberships, contexts = product
    service.notifications.create(tenant_id=tenant["id"], notification_type="system", severity="info", title="One", message="Message")
    subscription, _plan = service.quota.usage_service.subscription(tenant["id"])
    service.storage.update_by_id("tenant_subscriptions", subscription["id"], {"overrides_json": {"max_users": 4}})
    for _ in range(2):
        with pytest.raises(QuotaExceededError):
            service.quota.check_quota(tenant["id"], "users")
    assert service.storage.count("notifications", tenant_id=tenant["id"], filters={"type": "quota_exceeded"}) == 1
    config = ProductionConfig.from_env()
    client = TestClient(create_app(service=service, config=config))
    login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "pass123456"})
    assert login.status_code == 200
    page = client.get("/api/notifications?unread_only=true")
    assert page.status_code == 200 and page.json()["unread_count"] >= 1
    assert client.post("/api/notifications/read-all").status_code == 200
    assert client.get("/api/notifications?unread_only=true").json()["unread_count"] == 0


def test_system_admin_and_tenant_suspension(product):
    service, tenant, users, _memberships, contexts = product
    service.storage.update_by_id("users", users["owner"]["id"], {"is_system_admin": True})
    assert service.system_admin.list_tenants(users["owner"]["id"], limit=50, offset=0)["total"] == 1
    subscription, plan = service.quota.usage_service.subscription(tenant["id"])
    service.system_admin.update_subscription(users["owner"]["id"], tenant["id"], {"plan_id": plan["id"], "tenant_status": "suspended"})
    with pytest.raises(PermissionError, match="tenant_suspended"):
        service.create_campaign(contexts["owner"], {"name": "Blocked", "platform_account_id": "missing"})
    assert service.me(contexts["owner"])["tenant"]["status"] == "suspended"
    service.system_admin.update_subscription(users["owner"]["id"], tenant["id"], {"plan_id": plan["id"], "tenant_status": "active"})
    assert service.storage.get_by_id("tenants", tenant["id"])["status"] == "active"


def test_normal_user_cannot_access_admin_api(product):
    service, _tenant, _users, _memberships, _contexts = product
    client = TestClient(create_app(service=service, config=ProductionConfig.from_env()))
    assert client.post("/api/auth/login", json={"email": "member@example.com", "password": "pass123456"}).status_code == 200
    assert client.get("/api/admin/tenants").status_code == 403


def test_quota_api_returns_structured_429(product):
    service, tenant, _users, _memberships, _contexts = product
    subscription, _plan = service.quota.usage_service.subscription(tenant["id"])
    service.storage.update_by_id("tenant_subscriptions", subscription["id"], {"overrides_json": {"max_users": 4}})
    client = TestClient(create_app(service=service, config=ProductionConfig.from_env()))
    assert client.post("/api/auth/login", json={"email": "owner@example.com", "password": "pass123456"}).status_code == 200
    response = client.post("/api/tenant/invitations", json={"email": "over@example.com", "role": "member"})
    assert response.status_code == 429
    assert response.json()["error"] == {
        "code": "quota_exceeded",
        "message": "users quota reached",
        "resource": "users",
        "limit": 4,
        "used": 4,
    }


def test_execution_notification_failure_is_isolated(product, monkeypatch):
    service, tenant, _users, _memberships, _contexts = product
    execution = service.storage.insert("executions", {"tenant_id": tenant["id"], "campaign_id": "camp_missing", "platform": "facebook", "status": "completed", "send_disabled": True})
    monkeypatch.setattr(service.notifications, "create", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("notification unavailable")))
    service.notifications.execution_finished(execution)
    assert service.storage.get_by_id("executions", execution["id"])["status"] == "completed"
