from __future__ import annotations

import pytest

from src.facebook_leads.saas.seed import DEMO_ADMIN_EMAIL, demo_readiness_summary, seed_demo_data
from src.facebook_leads.saas.storage import SaaSStorage


def test_complete_demo_seed_is_idempotent_and_safe(tmp_path):
    storage = SaaSStorage(tmp_path / "demo.sqlite")

    first = seed_demo_data(storage, password="demo-password-123")
    first_counts = first["readiness"]["counts"]
    second = seed_demo_data(storage, password="demo-password-123")

    assert second["readiness"]["ready"] is True
    assert second["readiness"]["counts"] == first_counts
    assert second["readiness"]["campaign_statuses"] == {"active": 1, "paused": 1, "draft": 1}
    assert second["readiness"]["real_sends_enabled"] is False
    assert storage.count("tenant_users", tenant_id=first["tenant"]["id"]) == 2
    assert storage.count("tenant_invitations", tenant_id=first["tenant"]["id"], filters={"status": "pending"}) == 1
    assert all(row["send_disabled"] for row in storage.list("executions", tenant_id=first["tenant"]["id"]))
    assert storage.find_one("tenants", {"slug": "demo"})["tenant_reply_enabled"] is False
    assert {row["status"] for row in storage.list("reply_candidates", tenant_id=first["tenant"]["id"])} == {
        "pending_approval", "approved", "blocked"
    }
    assert storage.count("reply_records", tenant_id=first["tenant"]["id"], filters={"status": "blocked"}) == 1


def test_seed_requires_explicit_password(monkeypatch, tmp_path):
    monkeypatch.delenv("FACEBOOK_LEADS_DEMO_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="required"):
        seed_demo_data(SaaSStorage(tmp_path / "demo.sqlite"))


def test_readiness_summary_does_not_seed(tmp_path):
    storage = SaaSStorage(tmp_path / "empty.sqlite")
    assert demo_readiness_summary(storage) == {
        "ready": False,
        "tenant_id": None,
        "reason": "demo tenant not seeded",
        "counts": {},
        "real_sends_enabled": False,
    }
    assert storage.find_one("users", {"email": DEMO_ADMIN_EMAIL}) is None
