from __future__ import annotations

import asyncio
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import pytest

from src.facebook_leads.saas.models import TenantContext
from src.facebook_leads.saas.providers import FacebookProvider, InstagramProvider, OzonProvider, TikTokProvider, XProvider
from src.facebook_leads.saas.runtime import safe_runtime
from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage
from src.facebook_leads.saas.worker import ExecutionWorker


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
_TEST_URL = urlparse(TEST_DATABASE_URL or "")
_TEST_DB_NAME = (_TEST_URL.path or "").rsplit("/", 1)[-1]
_TEST_HOST = _TEST_URL.hostname or ""
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL
    or TEST_DATABASE_URL == os.getenv("DATABASE_URL")
    or not _TEST_DB_NAME.endswith("_test")
    or os.getenv("ALLOW_DESTRUCTIVE_DATABASE_TESTS") != "true"
    or _TEST_HOST not in {"127.0.0.1", "localhost", "::1"},
    reason="TEST_DATABASE_URL must point to a dedicated local PostgreSQL *_test database and ALLOW_DESTRUCTIVE_DATABASE_TESTS=true",
)


def make_postgres_service(tmp_path: Path) -> SaaSService:
    providers = {
        "facebook": FacebookProvider(runner=fake_runner_factory(tmp_path)),
        "instagram": InstagramProvider(),
        "x": XProvider(),
        "tiktok": TikTokProvider(),
        "ozon": OzonProvider(),
    }
    storage = SaaSStorage(TEST_DATABASE_URL, create_schema=False)
    return SaaSService(storage, providers=providers, artifacts_root=tmp_path / "artifacts", runtime_registry=FakeRuntimeRegistry(storage, tmp_path))


def create_workspace(service: SaaSService, *, slug: str):
    tenant = service.create_tenant(f"Tenant {slug}", slug)
    user = service.create_user(f"{slug}@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    session = service.login(f"{slug}@example.com", "pass123456")
    context = service.context_from_token(session["access_token"])
    account = service.create_platform_account(
        context,
        {"platform": "facebook", "display_name": "Facebook Page"},
    )
    service.runtime_registry.provision_logged_in(context, account["id"])
    account = service.storage.get_by_id("platform_accounts", account["id"], tenant_id=context.tenant_id) or account
    campaign = service.create_campaign(
        context,
        {"name": "Massage Chair", "platform_account_id": account["id"], "status": "active", "target_policy": "discovery_only"},
    )
    service.create_keyword(context, campaign["id"], {"keyword": "massage chair", "priority": 1})
    return context, account, campaign


class FakeRuntimeRegistry:
    def __init__(self, storage: SaaSStorage, tmp_path: Path) -> None:
        self.storage = storage
        self.tmp_path = tmp_path
        self.next_port = 9400

    def provision_logged_in(self, context: TenantContext, account_id: str):
        runtime = self.storage.insert(
            "browser_runtimes",
            {
                "tenant_id": context.tenant_id,
                "platform_account_id": account_id,
                "runtime_type": "browser_use_chromium_cdp",
                "status": "running",
                "profile_path": str(self.tmp_path / context.tenant_id / account_id / "profile"),
                "cdp_port": self.next_port,
                "cdp_url": f"http://127.0.0.1:{self.next_port}",
                "browser_pid": self.next_port + 10000,
            },
        )
        self.next_port += 1
        self.storage.update_by_id(
            "platform_accounts",
            account_id,
            {"browser_runtime_id": runtime["id"], "connection_status": "connected", "login_status": "logged_in"},
            tenant_id=context.tenant_id,
        )
        return runtime

    def get_runtime(self, context: TenantContext, account_id: str):
        return self.storage.find_one("browser_runtimes", {"tenant_id": context.tenant_id, "platform_account_id": account_id})

    def health_check(self, context: TenantContext, runtime_id: str):
        runtime = self.storage.get_by_id("browser_runtimes", runtime_id, tenant_id=context.tenant_id)
        return {"reachable": True, "status": "running", "runtime": safe_runtime(runtime)}

    def start_runtime(self, context: TenantContext, account_id: str):
        return self.get_runtime(context, account_id) or self.provision_logged_in(context, account_id)


def fake_runner_factory(tmp_path: Path):
    async def fake_runner(_config):
        run_dir = tmp_path / "pg_runner" / "run_fake"
        run_dir.mkdir(parents=True, exist_ok=True)
        report_path = run_dir / "lead_report_enriched.json"
        report_path.write_text(
            json.dumps(
                {
                    "contents": [
                        {
                            "leads": [
                                {
                                    "comment_id": "comment-1",
                                    "comment_fingerprint": "fp-1",
                                    "author_name": "Buyer One",
                                    "comment_text": "How much is this massage chair?",
                                    "source_content_url": "https://www.facebook.com/reel/1",
                                    "direct_comment_url": "https://www.facebook.com/reel/1?comment_id=comment-1",
                                    "rule_intent_level": "high",
                                    "reply_allowed": True,
                                    "ownership_status": "owned",
                                    "llm_review": {
                                        "confidence": 0.96,
                                        "intent_level": "high",
                                        "intent_types": ["explicit_price_query"],
                                        "suggested_reply": "Thanks, our team can share current options.",
                                    },
                                }
                            ]
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return {
            "run_id": "run_fake",
            "status": "completed",
            "stage": "completed",
            "started_at": "2026-07-22T00:00:00+00:00",
            "finished_at": "2026-07-22T00:00:01+00:00",
            "elapsed_ms": 1000,
            "scan_summary": {"scanned_contents": 1, "scanned_comments": 4, "lead_candidates": 1},
            "batch_plan_summary": {"eligible_count": 1, "selected_count": 1},
            "llm_review_summary": {
                "model": "test-model",
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "call_count": 1,
            },
            "paths": {"lead_report_enriched_json": str(report_path)},
            "send_disabled": True,
        }

    return fake_runner


@pytest.fixture(autouse=True)
def migrated_clean_database():
    env = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL or ""}
    subprocess.run(["py", "-m", "alembic", "upgrade", "head"], check=True, cwd=Path.cwd(), env=env)
    storage = SaaSStorage(TEST_DATABASE_URL, create_schema=False)
    for table in ["worker_heartbeats", "token_usage", "reply_records", "reply_candidates", "reply_plans", "reply_match_rules", "reply_templates", "execution_keywords", "execution_queue_items", "sessions", "executions", "lead_notes", "leads", "reply_rules", "campaign_keywords", "campaign_schedules", "campaigns", "browser_runtimes", "platform_accounts", "tenant_users", "users", "tenants"]:
        storage.execute(f"DELETE FROM {table}")
    yield


def test_postgres_migration_login_isolation_run_and_token_aggregation(tmp_path):
    service = make_postgres_service(tmp_path)
    ctx_a, _account_a, campaign_a = create_workspace(service, slug="pg-a")
    ctx_b, _account_b, campaign_b = create_workspace(service, slug="pg-b")

    with pytest.raises(PermissionError):
        service.list_keywords(ctx_b, campaign_a["id"])
    result = asyncio.run(service.run_campaign(ctx_a, campaign_a["id"]))
    asyncio.run(ExecutionWorker(service, worker_id="pg-worker").tick())

    assert result["send_disabled"] is True
    assert service.get_execution(ctx_a, result["execution_id"])["status"] == "completed"
    assert service.list_leads(ctx_a)["items"][0]["tenant_id"] == ctx_a.tenant_id
    assert service.list_leads(ctx_b)["items"] == []
    assert service.token_usage_summary(ctx_a)["this_month"] == 15
    assert service.token_usage_summary(ctx_b)["this_month"] == 0
    assert campaign_b["tenant_id"] == ctx_b.tenant_id


def test_postgres_concurrent_campaign_and_execution_writes(tmp_path):
    service = make_postgres_service(tmp_path)
    ctx_a, account_a, campaign_a = create_workspace(service, slug="concurrent-a")
    ctx_b, account_b, campaign_b = create_workspace(service, slug="concurrent-b")

    def create_campaign(context, account, index):
        return service.create_campaign(
            context,
            {
                "name": f"Concurrent {index}",
                "platform_account_id": account["id"],
                "status": "active",
                "target_policy": "discovery_only",
            },
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        campaigns = list(
            executor.map(
                lambda args: create_campaign(*args),
                [(ctx_a, account_a, 1), (ctx_b, account_b, 2)],
            )
        )
    assert {row["tenant_id"] for row in campaigns} == {ctx_a.tenant_id, ctx_b.tenant_id}

    with ThreadPoolExecutor(max_workers=2) as executor:
        runs = list(executor.map(lambda args: asyncio.run(service.run_campaign(*args)), [(ctx_a, campaign_a["id"]), (ctx_b, campaign_b["id"])]))
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _index: asyncio.run(ExecutionWorker(service, worker_id=f"pg-worker-{_index}").tick()), [1, 2]))
    assert all(run["send_disabled"] is True for run in runs)
    assert len(service.list_executions(ctx_a)) == 1
    assert len(service.list_executions(ctx_b)) == 1


def test_postgres_two_workers_claim_once_and_runtime_lock_is_cross_process(tmp_path):
    service = make_postgres_service(tmp_path)
    ctx, _account, campaign = create_workspace(service, slug="claim-once")
    queued = asyncio.run(service.run_campaign(ctx, campaign["id"]))
    storage_a = SaaSStorage(TEST_DATABASE_URL, create_schema=False)
    storage_b = SaaSStorage(TEST_DATABASE_URL, create_schema=False)

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda storage: storage.claim_queue_item(), [storage_a, storage_b]))

    claimed = [item for item in claims if item]
    assert [item["execution_id"] for item in claimed] == [queued["execution_id"]]

    first_lock = storage_a.acquire_runtime_lock("runtime-claim-once")
    try:
        assert first_lock is not None
        assert storage_b.acquire_runtime_lock("runtime-claim-once") is None
    finally:
        storage_a.release_runtime_lock(first_lock)
    second_lock = storage_b.acquire_runtime_lock("runtime-claim-once")
    assert second_lock is not None
    storage_b.release_runtime_lock(second_lock)


def test_postgres_campaign_detail_lead_crud_and_execution_artifacts(tmp_path):
    service = make_postgres_service(tmp_path)
    ctx, _account, campaign = create_workspace(service, slug="crud-a")
    lead = service.storage.insert(
        "leads",
        {
            "tenant_id": ctx.tenant_id,
            "campaign_id": campaign["id"],
            "platform_account_id": campaign["platform_account_id"],
            "platform": "facebook",
            "comment_fingerprint": "crud-fp",
            "comment_text": "How much?",
            "author_name": "Buyer",
            "final_intent_level": "high",
            "reply_allowed": True,
            "discovered_at": "2026-07-27T00:00:00+00:00",
        },
    )
    execution = service.storage.insert(
        "executions",
        {
            "tenant_id": ctx.tenant_id,
            "campaign_id": campaign["id"],
            "platform": "facebook",
            "status": "failed",
            "trigger_type": "manual",
            "error_type": "cdp_unreachable",
            "send_disabled": True,
        },
    )
    artifact_root = tmp_path / "artifacts" / "tenants" / ctx.tenant_id / "executions" / execution["id"]
    artifact_root.mkdir(parents=True)
    (artifact_root / "worker.log").write_text("Authorization: Bearer secret-token\nCookie: c_user=123; xs=abc\nok", encoding="utf-8")
    (artifact_root / "screen.png").write_bytes(b"png")

    detail = service.get_campaign_detail(ctx, campaign["id"])
    assigned = service.assign_lead(ctx, lead["id"], ctx.user_id)
    note = service.create_lead_note(ctx, lead["id"], {"note": "Call back"})
    contacted = service.mark_lead_contacted(ctx, lead["id"])
    retried = service.retry_execution(ctx, execution["id"])
    logs = service.execution_logs(ctx, execution["id"])
    screenshots = service.execution_artifacts(ctx, execution["id"], artifact_type="screenshot")

    assert detail["leads_count"] == 1
    assert assigned["status"] == "assigned"
    assert note["lead_id"] == lead["id"]
    assert contacted["status"] == "contacted"
    assert retried["send_disabled"] is True
    assert "[REDACTED]" in "\n".join(row["line"] for row in logs["items"])
    assert screenshots["items"][0]["type"] == "screenshot"


def test_postgres_cross_tenant_lead_rejection_and_completed_retry_guard(tmp_path):
    service = make_postgres_service(tmp_path)
    ctx_a, _account_a, campaign_a = create_workspace(service, slug="crud-guard-a")
    ctx_b, _account_b, _campaign_b = create_workspace(service, slug="crud-guard-b")
    lead = service.storage.insert(
        "leads",
        {
            "tenant_id": ctx_a.tenant_id,
            "campaign_id": campaign_a["id"],
            "platform_account_id": campaign_a["platform_account_id"],
            "platform": "facebook",
            "comment_fingerprint": "guard-fp",
            "discovered_at": "2026-07-27T00:00:00+00:00",
        },
    )
    completed = service.storage.insert(
        "executions",
        {
            "tenant_id": ctx_a.tenant_id,
            "campaign_id": campaign_a["id"],
            "platform": "facebook",
            "status": "completed",
            "trigger_type": "manual",
            "send_disabled": True,
        },
    )

    with pytest.raises(PermissionError):
        service.update_lead(ctx_b, lead["id"], {"status": "open"})
    with pytest.raises(Exception, match="execution_not_retryable"):
        service.retry_execution(ctx_a, completed["id"])
