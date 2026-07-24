from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.facebook_leads.saas.api import create_app
from src.facebook_leads.saas.models import TenantContext
from src.facebook_leads.saas.rbac import Permission, require_permission
from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage


def _workspace(tmp_path):
    service = SaaSService(SaaSStorage(tmp_path / "rbac.sqlite"))
    tenant = service.create_tenant("RBAC", "rbac")
    contexts = {}
    tokens = {}
    for role in ("owner", "admin", "member", "viewer"):
        user = service.create_user(f"{role}@example.com", "pass123456", role.title())
        service.add_user_to_tenant(tenant["id"], user["id"], role=role)
        login = service.login(f"{role}@example.com", "pass123456")
        contexts[role] = service.context_from_token(login["access_token"])
        tokens[role] = login["access_token"]
    account = service.create_platform_account(contexts["admin"], {"platform": "facebook", "display_name": "Page"})
    service.runtime_registry.create_runtime(contexts["admin"], account["id"])
    campaign = service.create_campaign(contexts["admin"], {"name": "Campaign", "platform_account_id": account["id"], "status": "active"})
    keyword = service.create_keyword(contexts["admin"], campaign["id"], {"keyword": "massage chair"})
    rule = service.create_reply_rule(
        contexts["admin"],
        {"campaign_id": campaign["id"], "name": "Manual", "reply_template": "Thanks", "approval_mode": "manual"},
    )
    execution = service.storage.insert(
        "executions",
        {"tenant_id": tenant["id"], "campaign_id": campaign["id"], "platform": "facebook", "status": "queued", "send_disabled": True},
    )
    return service, contexts, tokens, account, campaign, keyword, rule, execution


@pytest.mark.parametrize("role", ["owner", "admin"])
def test_owner_and_admin_have_all_business_permissions(role):
    context = TenantContext(tenant_id="tenant", user_id="user", role=role)

    for permission in Permission:
        require_permission(context, permission)


def test_member_can_read_and_run_but_cannot_control_runtime_or_delete_account(tmp_path, monkeypatch):
    service, contexts, _tokens, account, campaign, _keyword, _rule, _execution = _workspace(tmp_path)
    member = contexts["member"]
    monkeypatch.setattr(
        service,
        "_preflight_runtime",
        lambda context, _account, _campaign_id, **_kwargs: {
            "runtime": {"id": "runtime", "cdp_url": "http://127.0.0.1:9400", "profile_path": str(tmp_path)},
            "run_context": None,
        },
    )

    assert service.dashboard_summary(member)["active_campaigns"] == 1
    assert service.enqueue_campaign_execution(member, campaign["id"], trigger_type="manual")["send_disabled"] is True
    with pytest.raises(PermissionError, match="permission denied"):
        service.reset_platform_profile(member, account["id"], confirm="RESET PROFILE")
    with pytest.raises(PermissionError, match="permission denied"):
        service.delete_platform_account(member, account["id"])


def test_viewer_is_read_only_for_all_business_mutations(tmp_path):
    service, _contexts, tokens, account, campaign, keyword, rule, execution = _workspace(tmp_path)
    client = TestClient(create_app(service=service))
    headers = {"Authorization": f"Bearer {tokens['viewer']}"}

    get_paths = [
        "/api/dashboard/summary",
        "/api/platform-accounts",
        f"/api/platform-accounts/{account['id']}/runtime",
        "/api/campaigns",
        f"/api/campaigns/{campaign['id']}/keywords",
        f"/api/campaigns/{campaign['id']}/schedule",
        "/api/leads",
        "/api/reply-rules",
        "/api/executions",
        "/api/token-usage/summary",
        "/api/settings",
    ]
    for path in get_paths:
        assert client.get(path, headers=headers).status_code == 200, path

    mutations = [
        ("post", "/api/platform-accounts", {"platform": "facebook", "display_name": "Blocked"}),
        ("patch", f"/api/platform-accounts/{account['id']}", {"display_name": "Blocked"}),
        ("delete", f"/api/platform-accounts/{account['id']}", None),
        ("post", f"/api/platform-accounts/{account['id']}/connect", {}),
        ("post", f"/api/platform-accounts/{account['id']}/check-login", {}),
        ("post", f"/api/platform-accounts/{account['id']}/reconnect", {}),
        ("post", f"/api/platform-accounts/{account['id']}/stop-runtime", {}),
        ("post", f"/api/platform-accounts/{account['id']}/restart-runtime", {}),
        ("post", f"/api/platform-accounts/{account['id']}/reset-profile", {"confirm": "RESET PROFILE"}),
        ("post", "/api/campaigns", {"name": "Blocked", "platform_account_id": account["id"]}),
        ("patch", f"/api/campaigns/{campaign['id']}", {"name": "Blocked"}),
        ("delete", f"/api/campaigns/{campaign['id']}", None),
        ("post", f"/api/campaigns/{campaign['id']}/keywords", {"keyword": "blocked"}),
        ("patch", f"/api/keywords/{keyword['id']}", {"keyword": "blocked"}),
        ("delete", f"/api/keywords/{keyword['id']}", None),
        ("put", f"/api/campaigns/{campaign['id']}/schedule", {"enabled": True, "schedule_type": "interval", "interval_minutes": 60}),
        ("post", f"/api/campaigns/{campaign['id']}/schedule/disable", {}),
        ("post", "/api/reply-rules", {"campaign_id": campaign["id"], "name": "Blocked"}),
        ("patch", f"/api/reply-rules/{rule['id']}", {"name": "Blocked"}),
        ("delete", f"/api/reply-rules/{rule['id']}", None),
        ("post", f"/api/campaigns/{campaign['id']}/run", {}),
        ("post", f"/api/executions/{execution['id']}/cancel", {}),
    ]
    for method, path, payload in mutations:
        response = client.request(method, path, headers=headers, json=payload)
        assert response.status_code == 403, (method, path, response.text)
        assert response.json()["error"]["code"] == "permission_denied"


def test_cross_tenant_mutation_remains_not_found(tmp_path):
    service, contexts, tokens, _account, campaign, _keyword, _rule, _execution = _workspace(tmp_path)
    other = service.create_tenant("Other", "other")
    other_user = service.create_user("other@example.com", "pass123456", "Other")
    service.add_user_to_tenant(other["id"], other_user["id"], role="admin")
    other_token = service.login("other@example.com", "pass123456")["access_token"]
    client = TestClient(create_app(service=service))

    response = client.patch(
        f"/api/campaigns/{campaign['id']}",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"name": "Hidden"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
