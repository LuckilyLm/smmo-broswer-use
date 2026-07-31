from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from scripts.saas_cleanup_sessions import cleanup_sessions
from src.facebook_leads.saas.artifacts import atomic_write_json, load_json_safe, safe_artifact_path
from src.facebook_leads.saas.auth import MAX_PBKDF2_ITERATIONS, hash_password, needs_rehash, verify_password
from src.facebook_leads.saas.api import create_app
from src.facebook_leads.saas.config import ProductionConfig
from src.facebook_leads.saas.db import utc_now
from src.facebook_leads.saas.models import TenantContext
from src.facebook_leads.saas.persist import persist_orchestrator_result
from src.facebook_leads.saas.service import SaaSService, ServiceConflictError
from src.facebook_leads.saas.storage import CURRENT_SCHEMA_REVISION, SaaSStorage
from src.facebook_leads.saas.worker import ExecutionWorker


def make_service(tmp_path: Path, *, config: ProductionConfig | None = None) -> tuple[SaaSService, TenantContext]:
    service = SaaSService(SaaSStorage(tmp_path / "phase751.sqlite"), config=config)
    tenant = service.create_tenant("Tenant", "tenant")
    user = service.create_user("owner@example.com", "pass123456", "Owner")
    service.add_user_to_tenant(tenant["id"], user["id"], role="owner")
    token = service.login("owner@example.com", "pass123456")["access_token"]
    return service, service.context_from_token(token)


def workspace(service: SaaSService, context: TenantContext):
    account = service.create_platform_account(context, {"platform": "facebook", "display_name": "Page"})
    campaign = service.create_campaign(context, {"name": "Campaign", "platform_account_id": account["id"], "status": "active"})
    keyword = service.create_keyword(context, campaign["id"], {"keyword": "massage chair"})
    return account, campaign, keyword


def test_deployment_mode_validation_and_safe_runtime_capability(monkeypatch, tmp_path):
    monkeypatch.setattr("src.facebook_leads.saas.config.platform.system", lambda: "Linux")
    config = ProductionConfig.from_env({"SAAS_DEPLOYMENT_MODE": "control-plane-only", "SAAS_RUNTIME_HOST": "local"})
    service, context = make_service(tmp_path, config=config)
    account, _campaign, _keyword = workspace(service, context)
    client = TestClient(create_app(service=service, config=config))
    token = service.login("owner@example.com", "pass123456")["access_token"]
    response = client.get("/api/system/runtime-capabilities", headers={"Authorization": f"Bearer {token}"})
    assert response.json() == {
        "runtime_host": "local",
        "runtime_available": False,
        "browser_platform": "Linux",
        "local_browser_supported": True,
        "browser_backend": "browser-use",
        "browser_headless": True,
        "browser_cdp_base_url": "http://127.0.0.1",
    }
    unavailable = client.post(
        f"/api/platform-accounts/{account['id']}/connect",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert unavailable.status_code == 501
    assert unavailable.json()["error"]["code"] == "local_browser_runtime_not_supported"
    with pytest.raises(RuntimeError, match="SAAS_DEPLOYMENT_MODE"):
        ProductionConfig.from_env({"SAAS_DEPLOYMENT_MODE": "remote-agent"})


def test_session_rotation_revokes_old_session_and_switches_tenant(tmp_path):
    service, context = make_service(tmp_path)
    other = service.create_tenant("Other", "other")
    service.add_user_to_tenant(other["id"], context.user_id, role="member")
    old = service.login("owner@example.com", "pass123456")["access_token"]
    rotated = service.rotate_session(old, other["id"])
    assert rotated["access_token"] != old
    with pytest.raises(PermissionError):
        service.context_from_token(old)
    assert service.context_from_token(rotated["access_token"]).tenant_id == other["id"]


def test_session_cleanup_defaults_to_dry_run(tmp_path):
    service, _context = make_service(tmp_path)
    session = service.storage.list("sessions", limit=1)[0]
    service.storage.update_by_id("sessions", session["id"], {"expires_at": utc_now() - timedelta(seconds=1)})
    preview = cleanup_sessions(service.storage)
    assert preview == {"matched": 1, "deleted": 0, "dry_run": True}
    assert service.storage.get_by_id("sessions", session["id"])
    executed = cleanup_sessions(service.storage, execute=True)
    assert executed["deleted"] == 1
    assert not service.storage.get_by_id("sessions", session["id"])


def test_legacy_password_hash_upgrades_after_login(tmp_path):
    service, context = make_service(tmp_path)
    legacy = hash_password("pass123456", iterations=120_000)
    service.storage.update_by_id("users", context.user_id, {"password_hash": legacy})
    assert verify_password("pass123456", legacy)
    assert needs_rehash(legacy)
    service.login("owner@example.com", "pass123456")
    upgraded = service.storage.get_by_id("users", context.user_id)["password_hash"]
    assert not needs_rehash(upgraded)


@pytest.mark.parametrize(
    "malformed_hash",
    [
        None,
        123,
        "",
        "pbkdf2_sha256$310000$salt",
        "pbkdf2_sha256$310000$salt$digest$extra",
        "unknown$310000$00$" + "00" * 32,
        "pbkdf2_sha256$nope$00$" + "00" * 32,
        "pbkdf2_sha256$1.5$00$" + "00" * 32,
        "pbkdf2_sha256$-1$00$" + "00" * 32,
        "pbkdf2_sha256$0$00$" + "00" * 32,
        f"pbkdf2_sha256${MAX_PBKDF2_ITERATIONS + 1}$00$" + "00" * 32,
        "pbkdf2_sha256$999999999999999999999999999999999999$00$" + "00" * 32,
        "pbkdf2_sha256$1$zz$" + "00" * 32,
        "pbkdf2_sha256$1$00$zz",
        "pbkdf2_sha256$1$$" + "00" * 32,
        "pbkdf2_sha256$1$00$00",
    ],
)
def test_malformed_password_hashes_fail_closed(malformed_hash):
    assert verify_password("pass123456", malformed_hash) is False
    assert needs_rehash(malformed_hash) is True


def test_api_login_with_malformed_password_hash_returns_invalid_credentials(tmp_path):
    service, context = make_service(tmp_path)
    service.storage.update_by_id(
        "users",
        context.user_id,
        {"password_hash": f"pbkdf2_sha256${MAX_PBKDF2_ITERATIONS + 1}$00$" + "00" * 32},
    )
    response = TestClient(create_app(service=service)).post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "pass123456"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "invalid credentials"


def test_scheduler_trigger_unique_constraint_is_final_duplicate_defense(tmp_path):
    service, context = make_service(tmp_path)
    _account, campaign, _keyword = workspace(service, context)
    key = "same-window"

    def enqueue():
        try:
            return service.enqueue_campaign_execution(context, campaign["id"], trigger_type="scheduled", schedule_trigger_key=key)
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: enqueue(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert service.storage.count("execution_queue_items", filters={"schedule_trigger_key": key}) == 1


def test_worker_lost_retries_analysis_only_and_cancel_wins(tmp_path):
    service, context = make_service(tmp_path)
    _account, campaign, _keyword = workspace(service, context)
    execution = service.enqueue_campaign_execution(context, campaign["id"], trigger_type="manual")
    item = service.storage.claim_queue_item(worker_id="lost")
    old = utc_now() - timedelta(hours=8)
    service.storage.update_by_id("execution_queue_items", item["id"], {"started_at": old})
    service.storage.update_by_id("executions", execution["id"], {"status": "running"})
    assert service.storage.fail_stale_queue_items(
        stale_before=utc_now() - timedelta(hours=6),
        retry_analysis_only=True,
    ) == 1
    assert service.storage.get_by_id("execution_queue_items", item["id"])["status"] == "retry_waiting"

    service.storage.update_by_id("execution_queue_items", item["id"], {"status": "running"})
    service.storage.update_by_id("executions", execution["id"], {"status": "running", "cancel_requested": True})
    result = service._retry_queue_item(item, execution, "worker_lost", "lost")
    assert result["status"] == "cancelled"
    assert service.storage.get_by_id("executions", execution["id"])["status"] == "cancelled"


def test_delete_guards_and_campaign_archive(tmp_path):
    service, context = make_service(tmp_path)
    account, campaign, _keyword = workspace(service, context)
    with pytest.raises(ServiceConflictError, match="platform_account_in_use"):
        service.delete_platform_account(context, account["id"])
    execution = service.enqueue_campaign_execution(context, campaign["id"], trigger_type="manual")
    with pytest.raises(ServiceConflictError, match="campaign_has_active_execution"):
        service.delete_campaign(context, campaign["id"])
    service.cancel_execution(context, execution["id"])
    service.delete_campaign(context, campaign["id"])
    archived = service.storage.get_by_id("campaigns", campaign["id"])
    assert archived["status"] == "archived"
    assert archived["deleted_at"] is not None


def test_lead_upsert_preserves_manual_status_and_updates_scanner_fields(tmp_path):
    service, context = make_service(tmp_path)
    account, campaign, _keyword = workspace(service, context)
    base = {
        "tenant_id": context.tenant_id,
        "campaign_id": campaign["id"],
        "platform_account_id": account["id"],
        "platform": "facebook",
        "comment_fingerprint": "fingerprint",
        "comment_text": "first",
        "status": "new",
        "matched_search_keywords": ["one"],
        "discovered_at": utc_now(),
    }
    lead = service.storage.upsert_lead(base)
    service.storage.update_by_id("leads", lead["id"], {"status": "qualified"})
    updated = service.storage.upsert_lead({**base, "comment_text": "second", "status": "blocked", "matched_search_keywords": ["two"]})
    assert updated["status"] == "qualified"
    assert updated["comment_text"] == "second"
    assert updated["matched_search_keywords"] == ["one", "two"]


def test_pagination_caps_limit_and_request_validation(tmp_path):
    service, _context = make_service(tmp_path)
    config = ProductionConfig.from_env()
    client = TestClient(create_app(service=service, config=config))
    login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "pass123456"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    page = client.get("/api/campaigns?limit=1000000", headers=headers)
    assert page.status_code == 200
    assert page.json()["limit"] == 200
    invalid = client.post(
        "/api/campaigns",
        headers=headers,
        json={"name": "bad", "platform_account_id": "missing", "min_confidence": 2},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_request"


def test_execution_and_keyword_snapshot_are_immutable(tmp_path):
    service, context = make_service(tmp_path)
    _account, campaign, keyword = workspace(service, context)
    execution = service.enqueue_campaign_execution(context, campaign["id"], trigger_type="manual")
    service.update_campaign(context, campaign["id"], {"max_comments": 999})
    service.update_keyword(context, keyword["id"], {"keyword": "changed"})
    snapshot = service.get_execution(context, execution["id"])["config_snapshot"]
    assert snapshot["max_comments"] == 80
    assert snapshot["keywords"] == [{"id": keyword["id"], "keyword": "massage chair"}]


def test_token_usage_is_idempotent_and_calculates_cost_and_latency(tmp_path):
    service, context = make_service(tmp_path)
    account, campaign, keyword = workspace(service, context)
    execution = service.enqueue_campaign_execution(context, campaign["id"], trigger_type="manual")
    execution_keyword = service.storage.insert(
        "execution_keywords",
        {
            "tenant_id": context.tenant_id,
            "execution_id": execution["id"],
            "campaign_keyword_id": keyword["id"],
            "keyword": keyword["keyword"],
            "status": "running",
        },
    )
    result = {
        "status": "completed",
        "elapsed_ms": 900,
        "llm_review_summary": {
            "model": "gpt-5.5",
            "prompt_tokens": 1_000,
            "completion_tokens": 500,
            "total_tokens": 1_500,
            "call_count": 1,
            "elapsed_ms": 700,
        },
        "lead_report": {"contents": []},
    }
    for _attempt in range(2):
        persist_orchestrator_result(
            service.storage,
            tenant_id=context.tenant_id,
            campaign_id=campaign["id"],
            platform_account_id=account["id"],
            platform="facebook",
            result=result,
            execution_id=execution["id"],
            execution_keyword_id=execution_keyword["id"],
            keyword=keyword["keyword"],
            input_cost_per_1m=2.0,
            output_cost_per_1m=4.0,
        )
    rows = service.storage.list(
        "token_usage",
        tenant_id=context.tenant_id,
        filters={"execution_keyword_id": execution_keyword["id"]},
    )
    assert len(rows) == 1
    assert rows[0]["estimated_cost"] == pytest.approx(0.004)
    assert rows[0]["elapsed_ms"] == 700


def test_artifact_path_atomic_write_and_corrupt_fallback(tmp_path):
    target = safe_artifact_path(tmp_path, "tenants", "tena_123", "executions", "exec_123") / "job_state.json"
    atomic_write_json(target, {"status": "running"})
    assert json.loads(target.read_text(encoding="utf-8"))["status"] == "running"
    target.write_text("{broken", encoding="utf-8")
    assert load_json_safe(target, default={}) == {}
    with pytest.raises(ValueError):
        safe_artifact_path(tmp_path, "..", "outside")


def test_metadata_contains_required_phase751_constraints(tmp_path):
    storage = SaaSStorage(tmp_path / "schema.sqlite")
    inspector = inspect(storage.engine)
    execution_unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("execution_keywords")}
    token_indexes = {item["name"] for item in inspector.get_indexes("token_usage")}
    assert ("execution_id", "keyword") in execution_unique
    assert "uq_token_usage_execution_keyword" in token_indexes
    assert CURRENT_SCHEMA_REVISION == "011_nullable_reply_allowed"


def test_saas_ci_is_secret_safe_and_excludes_real_browser():
    workflow = Path(".github/workflows/saas-ci.yml").read_text(encoding="utf-8")
    assert "postgres:16" in workflow
    assert "python -m pytest tests/facebook_leads" in workflow
    assert "npm run build" in workflow
    assert "OPENAI_API_KEY" not in workflow
    assert "facebook_reply" not in workflow
    assert "Real browser and Facebook reply flows are intentionally excluded" in workflow
