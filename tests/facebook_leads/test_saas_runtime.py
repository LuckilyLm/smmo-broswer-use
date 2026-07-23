from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import src.facebook_leads.saas.runtime as runtime_module
from src.facebook_leads.saas.api import create_app
from src.facebook_leads.saas.models import TenantContext
from src.facebook_leads.saas.providers import FacebookProvider
from src.facebook_leads.saas.runtime import BrowserRuntimeRegistry
from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage
from src.facebook_leads.saas.worker import ExecutionWorker


def test_windows_pid_check_does_not_decode_localized_tasklist_output(monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows-specific PID probe")
    monkeypatch.setattr(runtime_module.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout=b'"chrome.exe","4508"'))

    assert runtime_module._pid_exists(4508) is True


def service_with_registry(tmp_path: Path, *, login_status: str = "logged_in", runner=None):
    storage = SaaSStorage(tmp_path / "saas.sqlite")

    async def login_checker(_cdp_url: str) -> str:
        return login_status

    registry = BrowserRuntimeRegistry(storage, profiles_root=tmp_path / "profiles", chrome_executable=str(tmp_path / "chrome.exe"), login_checker=login_checker)
    providers = {"facebook": FacebookProvider(runner=runner or fake_runner(tmp_path))}
    return SaaSService(storage, providers=providers, artifacts_root=tmp_path / "artifacts", runtime_registry=registry)


def workspace(service: SaaSService, slug: str = "tenant"):
    tenant = service.create_tenant(f"Tenant {slug}", slug)
    user = service.create_user(f"{slug}@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    session = service.login(f"{slug}@example.com", "pass123456")
    context = service.context_from_token(session["access_token"])
    account = service.create_platform_account(context, {"platform": "facebook", "display_name": f"Page {slug}"})
    campaign = service.create_campaign(context, {"name": "Massage Chair", "platform_account_id": account["id"], "status": "active", "target_policy": "discovery_only"})
    service.create_keyword(context, campaign["id"], {"keyword": "massage chair"})
    return context, account, campaign, session


def fake_runner(tmp_path: Path, *, delay: float = 0.0, seen_env: list[str] | None = None):
    async def run(_config):
        if delay:
            await asyncio.sleep(delay)
        if seen_env is not None:
            seen_env.append(os.environ.get("BROWSER_CDP", ""))
        run_dir = tmp_path / "runner" / f"run_{len(seen_env or [])}"
        run_dir.mkdir(parents=True, exist_ok=True)
        report_path = run_dir / "lead_report_enriched.json"
        report_path.write_text(
            json.dumps(
                {
                    "contents": [
                        {
                            "leads": [
                                {
                                    "comment_id": "c1",
                                    "comment_fingerprint": "fp1",
                                    "author_name": "Buyer",
                                    "comment_text": "Price please",
                                    "rule_intent_level": "high",
                                    "reply_allowed": True,
                                    "llm_review": {"confidence": 0.95, "intent_level": "high", "intent_types": ["explicit_price_query"]},
                                }
                            ]
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return {
            "run_id": "runtime_run",
            "status": "completed",
            "stage": "completed",
            "scan_summary": {"scanned_contents": 1, "scanned_comments": 1, "lead_candidates": 1},
            "batch_plan_summary": {"eligible_count": 1, "selected_count": 1},
            "llm_review_summary": {"model": "runtime-test", "total_tokens": 7, "call_count": 1},
            "paths": {"lead_report_enriched_json": str(report_path)},
            "send_disabled": True,
        }

    return run


class FakePopen:
    next_pid = 42000

    def __init__(self, *_args, **_kwargs):
        FakePopen.next_pid += 1
        self.pid = FakePopen.next_pid


def make_runtime_running(service: SaaSService, context: TenantContext, account: dict, monkeypatch) -> dict:
    Path(service.runtime_registry.chrome_executable).write_text("fake", encoding="utf-8")
    monkeypatch.setattr(runtime_module.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(runtime_module, "_terminate_process_tree", lambda _pid: None)
    monkeypatch.setattr(runtime_module, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(runtime_module, "_cdp_reachable", lambda _url: True)
    runtime = service.runtime_registry.start_runtime(context, account["id"])
    asyncio.run(service.check_platform_login(context, account["id"]))
    return runtime


def test_runtime_profile_and_port_isolation(tmp_path, monkeypatch):
    service = service_with_registry(tmp_path)
    ctx, account_a, _campaign, _session = workspace(service, "a")
    account_b = service.create_platform_account(ctx, {"platform": "facebook", "display_name": "Page B"})

    runtime_a = make_runtime_running(service, ctx, account_a, monkeypatch)
    runtime_b = make_runtime_running(service, ctx, account_b, monkeypatch)

    assert runtime_a["profile_path"] != runtime_b["profile_path"]
    assert runtime_a["cdp_port"] != runtime_b["cdp_port"]
    assert runtime_a["browser_pid"] != runtime_b["browser_pid"]
    assert f"tenant_{ctx.tenant_id}" in runtime_a["profile_path"]
    assert f"platform_account_{account_a['id']}" in runtime_a["profile_path"]


def test_runtime_start_stop_restart_and_missing_chrome(tmp_path, monkeypatch):
    service = service_with_registry(tmp_path)
    ctx, account, _campaign, _session = workspace(service)

    missing = service.runtime_registry.start_runtime(ctx, account["id"])
    assert missing["status"] == "error"
    assert "chrome" in (missing["last_error"] or "").lower()

    runtime = make_runtime_running(service, ctx, account, monkeypatch)
    assert runtime["status"] == "running"
    stopped = service.runtime_registry.stop_runtime(ctx, account["id"])
    assert stopped["status"] == "stopped"
    restarted = service.runtime_registry.restart_runtime(ctx, account["id"])
    assert restarted["status"] == "running"


def test_runtime_start_reports_cdp_timeout_and_stops_process(tmp_path, monkeypatch):
    service = service_with_registry(tmp_path)
    ctx, account, _campaign, _session = workspace(service, "cdp-timeout")
    Path(service.runtime_registry.chrome_executable).write_text("fake", encoding="utf-8")
    terminated: list[int] = []
    monkeypatch.setattr(runtime_module.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(runtime_module, "_wait_for_cdp", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(runtime_module, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(runtime_module, "_terminate_process_tree", terminated.append)

    runtime = service.runtime_registry.start_runtime(ctx, account["id"])

    assert runtime["status"] == "error"
    assert runtime["browser_pid"] is None
    assert runtime["last_error"] == "Chrome started but CDP did not become reachable"
    assert len(terminated) == 1


@pytest.mark.parametrize("login_status", ["logged_in", "logged_out", "checkpoint", "captcha"])
def test_login_statuses(tmp_path, monkeypatch, login_status):
    service = service_with_registry(tmp_path, login_status=login_status)
    ctx, account, _campaign, _session = workspace(service)
    make_runtime_running(service, ctx, account, monkeypatch)

    result = asyncio.run(service.check_platform_login(ctx, account["id"]))

    assert result["login_status"] == login_status
    assert result["connection_status"] == ("connected" if login_status == "logged_in" else "login_required")


def test_cdp_unreachable_and_crash_mark_unhealthy(tmp_path, monkeypatch):
    service = service_with_registry(tmp_path)
    ctx, account, _campaign, _session = workspace(service)
    runtime = make_runtime_running(service, ctx, account, monkeypatch)

    monkeypatch.setattr(runtime_module, "_cdp_reachable", lambda _url: False)
    health = service.runtime_registry.health_check(ctx, runtime["id"])

    assert health["status"] == "unhealthy"
    assert service.storage.get_by_id("browser_runtimes", runtime["id"], tenant_id=ctx.tenant_id)["status"] == "unhealthy"


def test_runtime_api_tenant_isolation_and_safe_fields(tmp_path, monkeypatch):
    service = service_with_registry(tmp_path)
    ctx_a, account_a, _campaign_a, session_a = workspace(service, "tenant-a")
    ctx_b, account_b, _campaign_b, session_b = workspace(service, "tenant-b")
    make_runtime_running(service, ctx_a, account_a, monkeypatch)
    make_runtime_running(service, ctx_b, account_b, monkeypatch)
    app = create_app(service=service)
    client = TestClient(app)

    headers_a = {"Authorization": f"Bearer {session_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {session_b['access_token']}"}
    own = client.get(f"/api/platform-accounts/{account_a['id']}/runtime", headers=headers_a)
    cross = client.get(f"/api/platform-accounts/{account_b['id']}/runtime", headers=headers_a)

    assert own.status_code == 200
    assert cross.status_code == 404
    assert "profile_path" not in own.json()
    assert "websocket" not in json.dumps(own.json()).lower()
    assert "cookie" not in json.dumps(own.json()).lower()
    assert client.get(f"/api/platform-accounts/{account_b['id']}/runtime", headers=headers_b).status_code == 200


def test_reset_profile_requires_confirmation(tmp_path, monkeypatch):
    service = service_with_registry(tmp_path)
    ctx, account, _campaign, _session = workspace(service)
    make_runtime_running(service, ctx, account, monkeypatch)

    with pytest.raises(Exception):
        service.reset_platform_profile(ctx, account["id"], confirm="wrong")
    reset = service.reset_platform_profile(ctx, account["id"], confirm="RESET PROFILE")
    assert reset["login_status"] == "unknown"
    assert "profile_path" not in reset["runtime"]


def test_campaign_run_uses_scoped_runtime_cdp_and_not_global_cdp(tmp_path, monkeypatch):
    seen_env: list[str] = []
    service = service_with_registry(tmp_path, runner=fake_runner(tmp_path, seen_env=seen_env))
    ctx, account, campaign, _session = workspace(service)
    runtime = make_runtime_running(service, ctx, account, monkeypatch)
    monkeypatch.setenv("BROWSER_CDP", "http://127.0.0.1:9222")

    result = asyncio.run(service.run_campaign(ctx, campaign["id"]))
    asyncio.run(ExecutionWorker(service, worker_id="runtime-worker").tick())

    assert result["send_disabled"] is True
    assert seen_env == [runtime["cdp_url"]]


def test_same_account_concurrent_run_blocked_and_different_account_allowed(tmp_path, monkeypatch):
    service = service_with_registry(tmp_path, runner=fake_runner(tmp_path, delay=0.05))
    ctx, account_a, campaign_a, _session = workspace(service, "lock-a")
    account_b = service.create_platform_account(ctx, {"platform": "facebook", "display_name": "Page B"})
    campaign_b = service.create_campaign(ctx, {"name": "Other", "platform_account_id": account_b["id"], "status": "active", "target_policy": "discovery_only"})
    service.create_keyword(ctx, campaign_b["id"], {"keyword": "massage chair"})
    make_runtime_running(service, ctx, account_a, monkeypatch)
    make_runtime_running(service, ctx, account_b, monkeypatch)

    asyncio.run(service.run_campaign(ctx, campaign_a["id"]))
    asyncio.run(service.run_campaign(ctx, campaign_a["id"]))
    service._runtime_locks.add(service.runtime_registry.get_runtime(ctx, account_a["id"])["id"])
    waiting = asyncio.run(ExecutionWorker(service, worker_id="runtime-worker").tick())
    service._runtime_locks.clear()
    assert waiting["status"] == "retry_waiting"
    assert waiting["error_type"] == "runtime_locked"

    different = [asyncio.run(service.run_campaign(ctx, campaign_a["id"])), asyncio.run(service.run_campaign(ctx, campaign_b["id"]))]
    asyncio.run(ExecutionWorker(service, worker_id="runtime-worker").tick())
    asyncio.run(ExecutionWorker(service, worker_id="runtime-worker").tick())
    assert all(item["send_disabled"] is True for item in different)
