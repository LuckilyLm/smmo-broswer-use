from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from src.facebook_leads.saas.api import create_app
from src.facebook_leads.saas.db import utc_now
from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage


def _session_workspace(tmp_path, *, must_change_password: bool = False):
    service = SaaSService(SaaSStorage(tmp_path / "sessions.sqlite"), session_ttl_hours=168, session_idle_timeout_hours=24)
    tenant = service.create_tenant("Sessions", "sessions")
    user = service.create_user(
        "session@example.com",
        "pass123456",
        "Session User",
        must_change_password=must_change_password,
    )
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    login = service.login("session@example.com", "pass123456")
    return service, tenant, user, login


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expires_at", lambda: utc_now() - timedelta(seconds=1)),
        ("last_seen_at", lambda: utc_now() - timedelta(hours=25)),
        ("revoked_at", utc_now),
    ],
)
def test_expired_idle_and_revoked_sessions_are_rejected(tmp_path, field, value):
    service, _tenant, _user, login = _session_workspace(tmp_path)
    service.storage.update_by_id("sessions", login["access_token"], {field: value()})

    with pytest.raises(PermissionError, match="invalid session"):
        service.context_from_token(login["access_token"])


@pytest.mark.parametrize("inactive_resource", ["user", "tenant", "membership"])
def test_user_tenant_and_membership_status_are_enforced(tmp_path, inactive_resource):
    service, tenant, user, login = _session_workspace(tmp_path)
    if inactive_resource == "user":
        service.storage.update_by_id("users", user["id"], {"status": "inactive"})
    elif inactive_resource == "tenant":
        service.storage.update_by_id("tenants", tenant["id"], {"status": "inactive"})
    else:
        membership = service.storage.find_one("tenant_users", {"tenant_id": tenant["id"], "user_id": user["id"]})
        service.storage.delete_by_id("tenant_users", membership["id"])

    with pytest.raises(PermissionError, match="invalid session"):
        service.context_from_token(login["access_token"])


def test_session_last_seen_uses_throttled_sliding_refresh(tmp_path):
    service, _tenant, _user, login = _session_workspace(tmp_path)
    old = utc_now() - timedelta(minutes=10)
    service.storage.update_by_id("sessions", login["access_token"], {"last_seen_at": old})

    service.context_from_token(login["access_token"])

    refreshed = service.storage.get_by_id("sessions", login["access_token"])
    assert refreshed["last_seen_at"] > old.isoformat()


def test_must_change_password_blocks_business_api_and_change_revokes_old_session(tmp_path):
    service, _tenant, user, login = _session_workspace(tmp_path, must_change_password=True)
    client = TestClient(create_app(service=service))
    headers = {"Authorization": f"Bearer {login['access_token']}"}

    assert client.get("/api/auth/me", headers=headers).status_code == 200
    blocked = client.get("/api/dashboard/summary", headers=headers)
    changed = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"current_password": "pass123456", "new_password": "newpass123456"},
    )

    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "password_change_required"
    assert changed.status_code == 200
    assert service.storage.get_by_id("users", user["id"])["must_change_password"] is False
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert service.login("session@example.com", "newpass123456")["access_token"]


def test_login_cookie_max_age_matches_session_ttl(tmp_path):
    service, _tenant, _user, _login = _session_workspace(tmp_path)
    client = TestClient(create_app(service=service))

    response = client.post("/api/auth/login", json={"email": "session@example.com", "password": "pass123456"})

    assert response.status_code == 200
    assert "Max-Age=604800" in response.headers["set-cookie"]
