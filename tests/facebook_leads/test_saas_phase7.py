from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.facebook_leads.facebook.orchestrator import FacebookLeadsRunConfig
from src.facebook_leads.saas.api import create_app
from src.facebook_leads.saas.db import utc_now
from src.facebook_leads.saas.models import TenantContext
from src.facebook_leads.saas.providers import FacebookProvider, InstagramProvider, OzonProvider, ProviderRunRequest, TikTokProvider, XProvider
from src.facebook_leads.saas.runtime import safe_runtime
from src.facebook_leads.saas.scheduler import CampaignScheduler
from src.facebook_leads.saas.seed import DEMO_ADMIN_EMAIL, seed_demo_data
from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage
from src.facebook_leads.saas.worker import ExecutionWorker


def make_service(tmp_path: Path, runner=None) -> SaaSService:
    storage = SaaSStorage(tmp_path / "saas.sqlite")
    providers = None
    if runner:
        providers = {
            "facebook": FacebookProvider(runner=runner),
            "instagram": InstagramProvider(),
            "x": XProvider(),
            "tiktok": TikTokProvider(),
            "ozon": OzonProvider(),
        }
    return SaaSService(storage, providers=providers, artifacts_root=tmp_path / "artifacts", runtime_registry=FakeRuntimeRegistry(storage, tmp_path))


def create_workspace(service: SaaSService, *, slug: str = "tenant-a") -> tuple[TenantContext, dict, dict]:
    tenant = service.create_tenant(f"Tenant {slug}", slug)
    user = service.create_user(f"{slug}@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    session = service.login(f"{slug}@example.com", "pass123456")
    context = service.context_from_token(session["access_token"])
    account = service.create_platform_account(
        context,
        {"platform": "facebook", "display_name": "Facebook Page"},
    )
    if hasattr(service.runtime_registry, "provision_logged_in"):
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
        self.next_port = 9300

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
                "browser_pid": 1000 + self.next_port,
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

    def get_runtime_by_id(self, context: TenantContext, runtime_id: str):
        return self.storage.get_by_id("browser_runtimes", runtime_id, tenant_id=context.tenant_id)

    def start_runtime(self, context: TenantContext, account_id: str, **_kwargs):
        runtime = self.get_runtime(context, account_id) or self.provision_logged_in(context, account_id)
        return self.storage.update_by_id("browser_runtimes", runtime["id"], {"status": "running"}, tenant_id=context.tenant_id) or runtime

    def stop_runtime(self, context: TenantContext, account_id: str):
        runtime = self.get_runtime(context, account_id)
        return self.storage.update_by_id("browser_runtimes", runtime["id"], {"status": "stopped"}, tenant_id=context.tenant_id) if runtime else {}

    def restart_runtime(self, context: TenantContext, account_id: str):
        return self.start_runtime(context, account_id)

    def reset_profile(self, context: TenantContext, account_id: str, *, confirm: str):
        if confirm != "RESET PROFILE":
            raise ValueError("confirmation required")
        return self.start_runtime(context, account_id)

    def health_check(self, context: TenantContext, runtime_id: str):
        runtime = self.get_runtime_by_id(context, runtime_id)
        return {"reachable": True, "status": "running", "runtime": safe_runtime(runtime)}

    async def check_login(self, context: TenantContext, account_id: str):
        account = self.storage.update_by_id("platform_accounts", account_id, {"login_status": "logged_in", "connection_status": "connected"}, tenant_id=context.tenant_id)
        return {"login_status": "logged_in", "connection_status": "connected", "account": account, "runtime": safe_runtime(self.get_runtime(context, account_id))}


def fake_runner_factory(tmp_path: Path, seen_configs: list[FacebookLeadsRunConfig] | None = None):
    async def fake_runner(config: FacebookLeadsRunConfig) -> dict:
        if seen_configs is not None:
            seen_configs.append(config)
        run_dir = tmp_path / "runner" / "run_fake"
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


def test_login_and_tenant_isolation(tmp_path):
    service = make_service(tmp_path)
    ctx_a, _account_a, campaign_a = create_workspace(service, slug="a")
    ctx_b, _account_b, _campaign_b = create_workspace(service, slug="b")

    assert service.me(ctx_a)["tenant"]["slug"] == "a"
    assert service.list_campaigns(ctx_b)[0]["tenant_id"] == ctx_b.tenant_id
    with pytest.raises(PermissionError):
        service.list_keywords(ctx_b, campaign_a["id"])


def test_platform_account_rejects_internal_secret_metadata(tmp_path):
    service = make_service(tmp_path)
    ctx, _account, _campaign = create_workspace(service)

    with pytest.raises(ValueError):
        service.create_platform_account(ctx, {"platform": "facebook", "display_name": "Bad", "api_key": "secret"})


def test_placeholder_providers_do_not_run(tmp_path):
    request = ProviderRunRequest(
        tenant_id="tenant",
        campaign_id="campaign",
        keyword="massage chair",
        target_policy="discovery_only",
        max_contents=5,
        max_comments=80,
        min_confidence=0.9,
        max_leads=5,
        daily_limit=10,
        llm_enabled=True,
        history_path=str(tmp_path / "history.jsonl"),
        runs_root=str(tmp_path / "runs"),
    )

    for provider in [InstagramProvider(), XProvider(), TikTokProvider(), OzonProvider()]:
        result = asyncio.run(provider.run_campaign(request))
        assert result["status"] == "not_implemented"
        assert result["send_disabled"] is True


def test_facebook_provider_reuses_orchestrator_config_and_forces_send_disabled(tmp_path):
    seen_configs: list[FacebookLeadsRunConfig] = []
    provider = FacebookProvider(runner=fake_runner_factory(tmp_path, seen_configs))

    result = asyncio.run(
        provider.run_campaign(
            ProviderRunRequest(
                tenant_id="tenant",
                campaign_id="campaign",
                keyword="massage chair",
                target_policy="discovery_only",
                max_contents=5,
                max_comments=80,
                min_confidence=0.9,
                max_leads=5,
                daily_limit=10,
                llm_enabled=True,
                history_path=str(tmp_path / "history.jsonl"),
                runs_root=str(tmp_path / "runs"),
            )
        )
    )

    assert seen_configs[0].keyword == "massage chair"
    assert seen_configs[0].min_confidence == 0.9
    assert result["send_disabled"] is True


def test_campaign_run_persists_execution_lead_and_token_usage(tmp_path):
    service = make_service(tmp_path, runner=fake_runner_factory(tmp_path))
    ctx, _account, campaign = create_workspace(service)

    result = asyncio.run(service.run_campaign(ctx, campaign["id"]))
    asyncio.run(ExecutionWorker(service, worker_id="test-worker").tick())

    assert result["send_disabled"] is True
    assert result["status"] == "queued"
    execution = service.get_execution(ctx, result["execution_id"])
    assert execution["send_disabled"] is True
    assert execution["status"] == "completed"
    leads = service.list_leads(ctx)["items"]
    assert len(leads) == 1
    assert leads[0]["comment_text"] == "How much is this massage chair?"
    assert service.token_usage_summary(ctx)["this_month"] == 15
    dashboard = service.dashboard_summary(ctx)
    assert dashboard["new_leads"] == 1
    assert dashboard["tokens_this_month"] == 15


def test_lead_pagination_filter_and_token_details_are_tenant_scoped(tmp_path):
    service = make_service(tmp_path, runner=fake_runner_factory(tmp_path))
    ctx_a, _account_a, campaign_a = create_workspace(service, slug="lead-a")
    ctx_b, _account_b, campaign_b = create_workspace(service, slug="lead-b")

    asyncio.run(service.run_campaign(ctx_a, campaign_a["id"]))
    asyncio.run(service.run_campaign(ctx_b, campaign_b["id"]))
    worker = ExecutionWorker(service, worker_id="test-worker")
    asyncio.run(worker.tick())
    asyncio.run(worker.tick())

    page = service.list_leads(ctx_a, {"keyword": "massage"}, limit=1, offset=0)
    assert len(page["items"]) == 1
    assert page["items"][0]["tenant_id"] == ctx_a.tenant_id
    details_a = service.token_usage_details(ctx_a)
    details_b = service.token_usage_details(ctx_b)
    assert details_a["by_model"][0]["total_tokens"] == 15
    assert details_a["by_campaign"][0]["campaign_name"] == campaign_a["name"]
    assert details_b["by_model"][0]["total_tokens"] == 15
    assert details_b["by_campaign"][0]["campaign_name"] == campaign_b["name"]


def test_saas_api_login_dashboard_and_campaign_run(tmp_path):
    service = make_service(tmp_path, runner=fake_runner_factory(tmp_path))
    seed_demo_data(service.storage, password="pass123456")
    seeded_session = service.login(DEMO_ADMIN_EMAIL, "pass123456")
    seeded_context = service.context_from_token(seeded_session["access_token"])
    seeded_account = service.list_platform_accounts(seeded_context)[0]
    service.runtime_registry.provision_logged_in(seeded_context, seeded_account["id"])
    service.logout(seeded_session["access_token"])
    app = create_app(service=service)
    client = TestClient(app)

    login = client.post("/api/auth/login", json={"email": DEMO_ADMIN_EMAIL, "password": "pass123456"})
    assert login.status_code == 200
    assert "httponly" in login.headers["set-cookie"].lower()
    assert "samesite=lax" in login.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    campaigns = client.get("/api/campaigns", headers=headers).json()
    run = client.post(f"/api/campaigns/{campaigns[0]['id']}/run", headers=headers)

    assert client.get("/api/dashboard/summary", headers=headers).status_code == 200
    assert run.status_code == 200
    assert run.json()["send_disabled"] is True
    assert run.json()["status"] == "queued"


def test_frontend_routes_and_no_internal_terms_exposed():
    app_path = Path("web/saas-dashboard/src/App.tsx")
    frontend_text = app_path.read_text(encoding="utf-8")

    for route in [
        "/login",
        "/change-password",
        "/dashboard",
        "/platform-accounts",
        "/campaigns",
        "/keywords",
        "/leads",
        "/reply-rules",
        "/executions",
        "/token-usage",
        "/settings",
    ]:
        assert route in frontend_text
    for forbidden in ["Browser Use", "Playwright", "CDP", "Cookie", "artifact", "Prompt", "CLI", "api_key"]:
        assert forbidden not in frontend_text


def test_manual_run_enqueues_once_and_worker_claims_one_item(tmp_path):
    service = make_service(tmp_path, runner=fake_runner_factory(tmp_path))
    ctx, _account, campaign = create_workspace(service)

    first = asyncio.run(service.run_campaign(ctx, campaign["id"]))
    second = asyncio.run(service.run_campaign(ctx, campaign["id"]))

    assert first["status"] == "queued"
    assert second["status"] == "queued"
    claimed = service.storage.claim_queue_item()
    assert claimed["execution_id"] == first["execution_id"]
    assert service.storage.claim_queue_item()["execution_id"] == second["execution_id"]
    assert service.storage.claim_queue_item() is None


def test_two_workers_cannot_claim_the_same_queue_item(tmp_path):
    service = make_service(tmp_path, runner=fake_runner_factory(tmp_path))
    ctx, _account, campaign = create_workspace(service)
    queued = asyncio.run(service.run_campaign(ctx, campaign["id"]))

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _worker: service.storage.claim_queue_item(), range(2)))

    claimed = [item for item in claims if item]
    assert [item["execution_id"] for item in claimed] == [queued["execution_id"]]


def test_tenant_control_fields_cannot_be_overridden(tmp_path):
    service = make_service(tmp_path)
    ctx_a, account_a, campaign_a = create_workspace(service, slug="guard-a")
    ctx_b, _account_b, _campaign_b = create_workspace(service, slug="guard-b")

    account = service.create_platform_account(ctx_a, {"tenant_id": ctx_b.tenant_id, "platform": "facebook", "display_name": "Guarded"})
    campaign = service.create_campaign(ctx_a, {"tenant_id": ctx_b.tenant_id, "name": "Guarded", "platform_account_id": account_a["id"]})
    keyword = service.create_keyword(ctx_a, campaign_a["id"], {"tenant_id": ctx_b.tenant_id, "campaign_id": _campaign_b["id"], "keyword": "guarded"})
    service.update_campaign(ctx_a, campaign_a["id"], {"tenant_id": ctx_b.tenant_id, "name": "Still A"})

    assert account["tenant_id"] == ctx_a.tenant_id
    assert campaign["tenant_id"] == ctx_a.tenant_id
    assert keyword["tenant_id"] == ctx_a.tenant_id
    assert keyword["campaign_id"] == campaign_a["id"]
    assert service.storage.get_by_id("campaigns", campaign_a["id"], tenant_id=ctx_a.tenant_id)["name"] == "Still A"


def test_scheduler_due_campaign_enqueues_once_and_skips_paused_or_disabled(tmp_path):
    service = make_service(tmp_path, runner=fake_runner_factory(tmp_path))
    ctx, _account, campaign = create_workspace(service)
    schedule = service.put_campaign_schedule(ctx, campaign["id"], {"enabled": True, "schedule_type": "interval", "interval_minutes": 60, "timezone": "Asia/Shanghai"})
    service.storage.update_by_id("campaign_schedules", schedule["id"], {"next_run_at": "2026-07-21T00:00:00+00:00"}, tenant_id=ctx.tenant_id)
    scheduler = CampaignScheduler(service)

    assert len(scheduler.tick()) == 1
    assert scheduler.tick() == []

    service.storage.update_by_id("campaign_schedules", schedule["id"], {"next_run_at": "2026-07-21T00:00:00+00:00"}, tenant_id=ctx.tenant_id)
    service.update_campaign(ctx, campaign["id"], {"status": "paused"})
    assert scheduler.tick() == []

    service.update_campaign(ctx, campaign["id"], {"status": "active"})
    service.disable_campaign_schedule(ctx, campaign["id"])
    assert scheduler.tick() == []


def test_scheduler_queue_full_uses_short_retry_without_marking_last_run(tmp_path):
    service = make_service(tmp_path, runner=fake_runner_factory(tmp_path))
    service.max_queued_executions_per_tenant = 1
    ctx, _account, campaign = create_workspace(service)
    service.enqueue_campaign_execution(ctx, campaign["id"], trigger_type="manual")
    schedule = service.put_campaign_schedule(
        ctx,
        campaign["id"],
        {"enabled": True, "schedule_type": "daily", "daily_time": "23:59", "timezone": "UTC"},
    )
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    service.storage.update_by_id("campaign_schedules", schedule["id"], {"next_run_at": due, "last_run_at": None}, tenant_id=ctx.tenant_id)
    before = datetime.now(timezone.utc)

    assert CampaignScheduler(service, queue_full_retry_minutes=5).tick() == []

    updated = service.storage.get_by_id("campaign_schedules", schedule["id"], tenant_id=ctx.tenant_id)
    retry_at = datetime.fromisoformat(updated["next_run_at"])
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    assert updated["last_run_at"] is None
    assert timedelta(minutes=4, seconds=50) <= retry_at - before <= timedelta(minutes=5, seconds=10)
    assert service.storage.count("executions", tenant_id=ctx.tenant_id) == 1


def test_scheduler_duplicate_advances_schedule_without_duplicate_execution(tmp_path):
    service = make_service(tmp_path, runner=fake_runner_factory(tmp_path))
    ctx, _account, campaign = create_workspace(service)
    schedule = service.put_campaign_schedule(
        ctx,
        campaign["id"],
        {"enabled": True, "schedule_type": "interval", "interval_minutes": 60, "timezone": "UTC"},
    )
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    service.storage.update_by_id("campaign_schedules", schedule["id"], {"next_run_at": due}, tenant_id=ctx.tenant_id)
    scheduler = CampaignScheduler(service)
    assert len(scheduler.tick()) == 1
    execution_count = service.storage.count("executions", tenant_id=ctx.tenant_id)
    service.storage.update_by_id("campaign_schedules", schedule["id"], {"next_run_at": due, "last_run_at": None}, tenant_id=ctx.tenant_id)

    assert scheduler.tick() == []

    updated = service.storage.get_by_id("campaign_schedules", schedule["id"], tenant_id=ctx.tenant_id)
    assert updated["last_run_at"] is not None
    assert service.storage.count("executions", tenant_id=ctx.tenant_id) == execution_count


def test_worker_heartbeat_keeps_long_running_item_out_of_stale_recovery(tmp_path):
    async def delayed_runner(config):
        await asyncio.sleep(0.12)
        return await fake_runner_factory(tmp_path)(config)

    service = make_service(tmp_path, runner=delayed_runner)
    ctx, _account, campaign = create_workspace(service)
    queued = asyncio.run(service.run_campaign(ctx, campaign["id"]))

    async def exercise():
        worker = ExecutionWorker(service, worker_id="heartbeat-worker", heartbeat_interval_seconds=0.01)
        task = asyncio.create_task(worker.tick())
        await asyncio.sleep(0.06)
        item = service.storage.find_one("execution_queue_items", {"execution_id": queued["execution_id"]})
        service.storage.update_by_id("execution_queue_items", item["id"], {"started_at": utc_now() - timedelta(hours=8)})
        heartbeat = service.storage.find_one("worker_heartbeats", {"worker_id": "heartbeat-worker"})
        heartbeat_seen = datetime.fromisoformat(heartbeat["last_seen_at"])
        if heartbeat_seen.tzinfo is None:
            heartbeat_seen = heartbeat_seen.replace(tzinfo=timezone.utc)
        recovered = service.storage.fail_stale_queue_items(
            stale_before=utc_now() - timedelta(hours=6),
            heartbeat_stale_before=heartbeat_seen - timedelta(seconds=1),
        )
        result = await task
        return recovered, result

    recovered, result = asyncio.run(exercise())

    assert recovered == 0
    assert result["status"] == "completed"


def test_multi_keyword_run_aggregates_tokens_and_dedups_leads(tmp_path):
    seen_configs: list[FacebookLeadsRunConfig] = []
    service = make_service(tmp_path, runner=fake_runner_factory(tmp_path, seen_configs))
    ctx, _account, campaign = create_workspace(service)
    service.create_keyword(ctx, campaign["id"], {"keyword": "massage chair price", "priority": 2})
    service.create_keyword(ctx, campaign["id"], {"keyword": "massage recliner", "priority": 3})

    queued = asyncio.run(service.run_campaign(ctx, campaign["id"]))
    asyncio.run(ExecutionWorker(service, worker_id="multi-worker").tick())

    execution = service.get_execution(ctx, queued["execution_id"])
    keywords = service.list_execution_keywords(ctx, queued["execution_id"])
    leads = service.list_leads(ctx)["items"]
    assert [config.keyword for config in seen_configs] == ["massage chair", "massage chair price", "massage recliner"]
    assert execution["status"] == "completed"
    assert execution["total_keywords"] == 3
    assert execution["completed_keywords"] == 3
    assert execution["scanned_comments"] == 12
    assert execution["total_tokens"] == 45
    assert service.token_usage_summary(ctx)["this_month"] == 45
    assert [row["status"] for row in keywords] == ["completed", "completed", "completed"]
    assert len(leads) == 1
    assert leads[0]["matched_search_keywords"] == ["massage chair", "massage chair price", "massage recliner"]
    assert leads[0]["first_discovered_at"]
    assert leads[0]["last_discovered_at"]


def test_keyword_failure_isolation_marks_execution_partial(tmp_path):
    async def runner(config: FacebookLeadsRunConfig) -> dict:
        if config.keyword == "broken keyword":
            raise RuntimeError("Page.goto timeout")
        return await fake_runner_factory(tmp_path)(config)

    service = make_service(tmp_path, runner=runner)
    ctx, _account, campaign = create_workspace(service)
    service.create_keyword(ctx, campaign["id"], {"keyword": "broken keyword", "priority": 2})
    service.create_keyword(ctx, campaign["id"], {"keyword": "massage recliner", "priority": 3})

    queued = asyncio.run(service.run_campaign(ctx, campaign["id"]))
    asyncio.run(ExecutionWorker(service, worker_id="partial-worker").tick())

    execution = service.get_execution(ctx, queued["execution_id"])
    keyword_rows = service.list_execution_keywords(ctx, queued["execution_id"])
    assert execution["status"] == "partial"
    assert execution["completed_keywords"] == 2
    assert execution["failed_keywords"] == 1
    assert [row["status"] for row in keyword_rows] == ["completed", "failed", "completed"]


def test_all_keyword_failures_mark_execution_failed_and_terminal_cancel_is_noop(tmp_path):
    async def failing_runner(_config: FacebookLeadsRunConfig) -> dict:
        raise RuntimeError("permanent provider error")

    service = make_service(tmp_path, runner=failing_runner)
    ctx, _account, campaign = create_workspace(service)
    service.create_keyword(ctx, campaign["id"], {"keyword": "also broken", "priority": 2})
    queued = asyncio.run(service.run_campaign(ctx, campaign["id"]))
    asyncio.run(ExecutionWorker(service, worker_id="failed-worker").tick())

    execution = service.get_execution(ctx, queued["execution_id"])
    cancelled = service.cancel_execution(ctx, queued["execution_id"])
    assert execution["status"] == "failed"
    assert execution["failed_keywords"] == 2
    assert cancelled["status"] == "failed"
    assert cancelled["cancel_requested"] is False


def test_all_retryable_keyword_failures_wait_30_seconds(tmp_path):
    async def timeout_runner(_config: FacebookLeadsRunConfig) -> dict:
        raise RuntimeError("Page.goto timeout")

    service = make_service(tmp_path, runner=timeout_runner)
    ctx, _account, campaign = create_workspace(service)
    queued = asyncio.run(service.run_campaign(ctx, campaign["id"]))
    before = datetime.now(timezone.utc)
    asyncio.run(ExecutionWorker(service, worker_id="retry-worker").tick())

    execution = service.get_execution(ctx, queued["execution_id"])
    queue = execution["queue"]
    run_after = datetime.fromisoformat(str(queue["run_after"]).replace("Z", "+00:00"))
    if run_after.tzinfo is None:
        run_after = run_after.replace(tzinfo=timezone.utc)
    delay = run_after - before
    assert execution["status"] == "queued"
    assert queue["status"] == "retry_waiting"
    assert 25 <= delay.total_seconds() <= 35
    assert service.list_execution_keywords(ctx, queued["execution_id"]) == []
