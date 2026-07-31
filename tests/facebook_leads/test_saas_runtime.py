from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient

import src.facebook_leads.saas.runtime as runtime_module
from src.facebook_leads.saas.api import create_app
from src.facebook_leads.saas.models import TenantContext
from src.facebook_leads.saas.providers import FacebookProvider
from src.facebook_leads.saas.runtime import BrowserRuntimeRegistry
from urllib.request import Request
from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage
from src.facebook_leads.saas.worker import ExecutionWorker


def test_cdp_proxy_rewrites_host_header_and_releases_port():
    upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    upstream.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    upstream.bind(("127.0.0.1", 0))
    port = upstream.getsockname()[1]
    upstream.listen(1)
    captured: list[bytes] = []

    def serve_once():
        client, _ = upstream.accept()
        with client:
            data = client.recv(4096)
            captured.append(data)
            body = (
                b'{"webSocketDebuggerUrl":"ws://127.0.0.1:'
                + str(port).encode("ascii")
                + b'/devtools/browser/test"}'
            )
            client.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body)

    thread = threading.Thread(target=serve_once, daemon=True)
    thread.start()
    proxy = runtime_module._CdpPortForwarder(bind_host="127.0.0.2", port=port)
    proxy.start()
    try:
        with socket.create_connection(("127.0.0.2", port), timeout=3) as client:
            client.sendall(b"GET /json/version HTTP/1.1\r\nHost: saas-browser-runtime:9999\r\nConnection: close\r\n\r\n")
            response = client.recv(4096)
            assert b"200 OK" in response
            expected_body = b'{"webSocketDebuggerUrl":"ws://127.0.0.2:' + str(port).encode("ascii") + b'/devtools/browser/test"}'
            assert expected_body in response
            assert b"ws://127.0.0.1:" not in response
            assert b"Content-Length: " + str(len(expected_body)).encode("ascii") in response
        thread.join(timeout=3)
        assert captured
        assert b"Host: 127.0.0.1:" + str(port).encode("ascii") in captured[0]
        assert b"saas-browser-runtime" not in captured[0]
    finally:
        proxy.close()
        upstream.close()

    deadline = time.time() + 3
    while True:
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.2", port))
            probe.close()
            break
        except OSError:
            if time.time() > deadline:
                raise
            time.sleep(0.05)


def test_cdp_proxy_buffers_split_initial_headers():
    upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    upstream.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    upstream.bind(("127.0.0.1", 0))
    port = upstream.getsockname()[1]
    upstream.listen(1)
    captured: list[bytes] = []

    def serve_once():
        client, _ = upstream.accept()
        with client:
            data = client.recv(4096)
            captured.append(data)
            client.sendall(b"HTTP/1.1 101 Switching Protocols\r\nContent-Length: 0\r\n\r\n")

    thread = threading.Thread(target=serve_once, daemon=True)
    thread.start()
    proxy = runtime_module._CdpPortForwarder(bind_host="127.0.0.2", port=port)
    proxy.start()
    try:
        with socket.create_connection(("127.0.0.2", port), timeout=3) as client:
            client.sendall(b"GET /devtools/browser/test HTTP/1.1\r\nHo")
            time.sleep(0.05)
            client.sendall(b"st: saas-browser-runtime:9999\r\nOrigin: http://saas-browser-runtime:9999\r\nUpgrade: websocket\r\n\r\n")
            assert b"101 Switching Protocols" in client.recv(4096)
        thread.join(timeout=3)
        assert captured
        assert b"Host: 127.0.0.1:" + str(port).encode("ascii") in captured[0]
        assert b"Origin: http://127.0.0.1:" + str(port).encode("ascii") in captured[0]
        assert b"saas-browser-runtime" not in captured[0]
    finally:
        proxy.close()
        upstream.close()


def test_runtime_retries_cdp_port_unique_collision(tmp_path, monkeypatch):
    storage = SaaSStorage(tmp_path / "collision.sqlite")
    registry = BrowserRuntimeRegistry(storage, profiles_root=tmp_path / "profiles", cdp_port_start=9400, cdp_port_end=9401)
    service = SaaSService(storage, runtime_registry=registry)
    tenant = service.create_tenant("Collision", "collision")
    user = service.create_user("collision@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    context = service.context_from_token(service.login("collision@example.com", "pass123456")["access_token"])
    account = service.create_platform_account(context, {"platform": "facebook", "display_name": "Page"})
    ports = iter([9400, 9401])
    monkeypatch.setattr(registry, "allocate_port", lambda: next(ports))
    original_insert = storage.insert
    calls = 0

    def insert_with_collision(table, data):
        nonlocal calls
        if table == "browser_runtimes" and calls == 0:
            calls += 1
            raise IntegrityError("insert", {}, Exception("unique cdp_port"))
        return original_insert(table, data)

    monkeypatch.setattr(storage, "insert", insert_with_collision)

    runtime = registry.create_runtime(context, account["id"])

    assert runtime["cdp_port"] == 9401
    assert calls == 1


def test_remote_control_sends_bearer_secret(tmp_path, monkeypatch):
    registry = BrowserRuntimeRegistry(
        SaaSStorage(tmp_path / "remote-auth.sqlite"),
        runtime_host="remote",
        remote_control_url="http://saas-browser-runtime:8001",
        remote_control_secret="shared-runtime-secret",
        allow_chrome_discovery=False,
    )
    captured: list[Request] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request: Request, timeout: int):
        captured.append(request)
        assert timeout == 30
        return Response()

    monkeypatch.setattr(runtime_module, "urlopen", fake_urlopen)

    assert registry._remote_control("POST", "/internal/runtime/tenant/account/stop", {}) == {}
    assert captured[0].get_header("Authorization") == "Bearer shared-runtime-secret"


def test_remote_runtime_registers_service_cdp_and_delegates_controls(tmp_path, monkeypatch):
    storage = SaaSStorage(tmp_path / "remote.sqlite")
    registry = BrowserRuntimeRegistry(
        storage,
        profiles_root=tmp_path / "profiles",
        cdp_port_start=9300,
        cdp_port_end=9300,
        runtime_host="remote",
        cdp_base_url="http://saas-browser-runtime",
        remote_control_url="http://saas-browser-runtime:8001",
    )
    service = SaaSService(storage, runtime_registry=registry)
    tenant = service.create_tenant("Remote", "remote")
    user = service.create_user("remote@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    context = service.context_from_token(service.login("remote@example.com", "pass123456")["access_token"])
    account = service.create_platform_account(context, {"platform": "facebook", "display_name": "Page"})
    calls: list[tuple[str, str, dict]] = []

    def remote_control(method: str, path: str, payload: dict):
        calls.append((method, path, payload))
        runtime = registry.get_runtime(context, account["id"])
        if path.endswith("/start") and runtime:
            storage.update_by_id("browser_runtimes", runtime["id"], {"status": "running", "browser_pid": 123}, tenant_id=context.tenant_id)
        if path.endswith("/stop") and runtime:
            storage.update_by_id("browser_runtimes", runtime["id"], {"status": "stopped", "browser_pid": None}, tenant_id=context.tenant_id)
        if path.endswith("/check-login"):
            storage.update_by_id("platform_accounts", account["id"], {"login_status": "logged_in", "connection_status": "connected"}, tenant_id=context.tenant_id)
        return {}

    monkeypatch.setattr(registry, "_remote_control", remote_control)

    runtime = registry.start_runtime(context, account["id"])
    assert runtime["cdp_url"] == "http://saas-browser-runtime:9300"
    assert runtime["status"] == "running"
    assert calls[0] == ("POST", f"/internal/runtime/{context.tenant_id}/{account['id']}/start", {"url": "https://www.facebook.com/"})

    login = asyncio.run(registry.check_login(context, account["id"]))
    assert login["login_status"] == "logged_in"
    assert calls[-1] == ("POST", f"/internal/runtime/{context.tenant_id}/{account['id']}/check-login", {})

    stopped = registry.stop_runtime(context, account["id"])
    assert stopped["status"] == "stopped"
    assert calls[-1] == ("POST", f"/internal/runtime/{context.tenant_id}/{account['id']}/stop", {})


def service_with_registry(tmp_path: Path, *, login_status: str = "logged_in", runner=None):
    storage = SaaSStorage(tmp_path / "saas.sqlite")

    async def login_checker(_cdp_url: str) -> str:
        return login_status

    registry = BrowserRuntimeRegistry(storage, profiles_root=tmp_path / "profiles", chrome_executable=str(tmp_path / "chromium"), login_checker=login_checker)
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


def fake_runner(tmp_path: Path, *, delay: float = 0.0, seen_configs: list | None = None):
    async def run(config):
        if delay:
            await asyncio.sleep(delay)
        if seen_configs is not None:
            seen_configs.append(config)
        run_dir = tmp_path / "runner" / f"run_{len(seen_configs or [])}"
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


def make_runtime_running(service: SaaSService, context: TenantContext, account: dict, monkeypatch) -> dict:
    async def fake_start_browser_use(_runtime, *, url):
        del url

    monkeypatch.setattr(service.runtime_registry, "_start_browser_use", fake_start_browser_use)
    monkeypatch.setattr(service.runtime_registry, "_close_session", lambda _runtime_id: None)
    monkeypatch.setattr(runtime_module, "_wait_for_cdp", lambda *_args, **_kwargs: True)
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
    assert runtime_a["browser_pid"]
    assert runtime_b["browser_pid"]
    assert f"tenant_{ctx.tenant_id}" in runtime_a["profile_path"]
    assert f"platform_account_{account_a['id']}" in runtime_a["profile_path"]


def test_runtime_start_stop_restart_and_missing_chrome(tmp_path, monkeypatch):
    service = service_with_registry(tmp_path)
    ctx, account, _campaign, _session = workspace(service)

    missing = service.runtime_registry.start_runtime(ctx, account["id"])
    assert missing["status"] == "error"
    assert "filenotfounderror" in (missing["last_error"] or "").lower()

    runtime = make_runtime_running(service, ctx, account, monkeypatch)
    assert runtime["status"] == "running"
    stopped = service.runtime_registry.stop_runtime(ctx, account["id"])
    assert stopped["status"] == "stopped"
    restarted = service.runtime_registry.restart_runtime(ctx, account["id"])
    assert restarted["status"] == "running"


def test_runtime_start_reports_cdp_timeout_and_stops_process(tmp_path, monkeypatch):
    service = service_with_registry(tmp_path)
    ctx, account, _campaign, _session = workspace(service, "cdp-timeout")

    async def fake_start_browser_use(_runtime, *, url):
        del url

    monkeypatch.setattr(service.runtime_registry, "_start_browser_use", fake_start_browser_use)
    monkeypatch.setattr(runtime_module, "_wait_for_cdp", lambda *_args, **_kwargs: False)

    runtime = service.runtime_registry.start_runtime(ctx, account["id"])

    assert runtime["status"] == "error"
    assert runtime["browser_pid"] is None
    assert runtime["last_error"] == "browser-use started but CDP did not become reachable"


@pytest.mark.parametrize("login_status", ["logged_in", "logged_out", "checkpoint", "captcha"])
def test_login_statuses(tmp_path, monkeypatch, login_status):
    service = service_with_registry(tmp_path, login_status=login_status)
    ctx, account, _campaign, _session = workspace(service)
    make_runtime_running(service, ctx, account, monkeypatch)

    result = asyncio.run(service.check_platform_login(ctx, account["id"]))

    assert result["login_status"] == login_status
    assert result["connection_status"] == ("connected" if login_status == "logged_in" else "login_required")


def test_platform_account_list_reconciles_connected_login_status(tmp_path):
    service = service_with_registry(tmp_path)
    ctx, account, _campaign, _session = workspace(service)
    service.storage.update_by_id(
        "platform_accounts",
        account["id"],
        {"login_status": "logged_in", "connection_status": "login_required"},
        tenant_id=ctx.tenant_id,
    )

    accounts = service.list_platform_accounts(ctx)

    listed = next(item for item in accounts if item["id"] == account["id"])
    persisted = service.storage.get_by_id("platform_accounts", account["id"], tenant_id=ctx.tenant_id)
    assert listed["login_status"] == "logged_in"
    assert listed["connection_status"] == "connected"
    assert persisted["connection_status"] == "connected"


def test_runtime_restores_login_state_snapshot_from_account_profile(tmp_path):
    storage = SaaSStorage(tmp_path / "snapshot.sqlite")
    registry = BrowserRuntimeRegistry(storage, profiles_root=tmp_path / "profiles")
    profile = tmp_path / "profiles" / "tenant_tenant_1" / "platform_account_account_1" / "profile"
    profile.mkdir(parents=True)
    snapshot = profile / "saas_login_state.json"
    snapshot.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "c_user",
                        "value": "123",
                        "domain": ".facebook.com",
                        "path": "/",
                        "expires": -1,
                        "httpOnly": True,
                        "secure": True,
                        "sameSite": "Lax",
                    }
                ],
                "origins": [],
            }
        ),
        encoding="utf-8",
    )

    class FakeContext:
        def __init__(self):
            self.cookies = []

        async def add_cookies(self, cookies):
            self.cookies.extend(cookies)

    class FakeBrowser:
        def __init__(self):
            self.contexts = [FakeContext()]

    fake_browser = FakeBrowser()

    asyncio.run(
        registry._restore_login_state_snapshot(
            {"id": "runtime_1", "tenant_id": "tenant_1", "platform_account_id": "account_1", "profile_path": str(profile)},
            fake_browser,
        )
    )

    assert fake_browser.contexts[0].cookies[0]["name"] == "c_user"


def test_cdp_unreachable_and_crash_mark_unhealthy(tmp_path, monkeypatch):
    service = service_with_registry(tmp_path)
    ctx, account, _campaign, _session = workspace(service)
    runtime = make_runtime_running(service, ctx, account, monkeypatch)

    monkeypatch.setattr(runtime_module, "_cdp_reachable", lambda _url: False)
    health = service.runtime_registry.health_check(ctx, runtime["id"])

    assert health["status"] == "unhealthy"
    assert service.storage.get_by_id("browser_runtimes", runtime["id"], tenant_id=ctx.tenant_id)["status"] == "unhealthy"

    service.storage.update_by_id(
        "browser_runtimes",
        runtime["id"],
        {"status": "running", "browser_pid": 99999},
        tenant_id=ctx.tenant_id,
    )
    crashed = service.runtime_registry.reconcile_runtime(ctx, runtime["id"])

    assert crashed["status"] == "unhealthy"


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


def test_campaign_run_uses_explicit_runtime_cdp_and_not_global_cdp(tmp_path, monkeypatch):
    seen_configs: list = []
    service = service_with_registry(tmp_path, runner=fake_runner(tmp_path, seen_configs=seen_configs))
    ctx, account, campaign, _session = workspace(service)
    runtime = make_runtime_running(service, ctx, account, monkeypatch)
    monkeypatch.setenv("BROWSER_CDP", "http://127.0.0.1:9222")

    result = asyncio.run(service.run_campaign(ctx, campaign["id"]))
    asyncio.run(ExecutionWorker(service, worker_id="runtime-worker").tick())

    assert result["send_disabled"] is True
    assert [config.cdp_url for config in seen_configs] == [runtime["cdp_url"]]
    assert os.environ["BROWSER_CDP"] == "http://127.0.0.1:9222"


def test_concurrent_runtimes_keep_explicit_cdp_isolated(tmp_path, monkeypatch):
    seen: dict[str, str | None] = {}

    async def runner(config):
        await asyncio.sleep(0.02)
        seen[str(config.keyword)] = config.cdp_url
        return await fake_runner(tmp_path)(config)

    service = service_with_registry(tmp_path, runner=runner)
    ctx, account_a, campaign_a, _session = workspace(service, "concurrent-cdp")
    account_b = service.create_platform_account(ctx, {"platform": "facebook", "display_name": "Page B"})
    campaign_b = service.create_campaign(ctx, {"name": "Other", "platform_account_id": account_b["id"], "status": "active", "target_policy": "discovery_only"})
    service.create_keyword(ctx, campaign_b["id"], {"keyword": "massage chair price"})
    runtime_a = make_runtime_running(service, ctx, account_a, monkeypatch)
    runtime_b = make_runtime_running(service, ctx, account_b, monkeypatch)
    monkeypatch.setenv("BROWSER_CDP", "http://global:9222")

    async def queue_both():
        return await asyncio.gather(service.run_campaign(ctx, campaign_a["id"]), service.run_campaign(ctx, campaign_b["id"]))

    queued_a, queued_b = asyncio.run(queue_both())
    items = [service.storage.claim_queue_item(worker_id="a"), service.storage.claim_queue_item(worker_id="b")]

    async def run_both():
        return await asyncio.gather(*(service.run_queue_item(item) for item in items if item))

    asyncio.run(run_both())

    assert queued_a["send_disabled"] is True and queued_b["send_disabled"] is True
    assert seen == {"massage chair": runtime_a["cdp_url"], "massage chair price": runtime_b["cdp_url"]}
    assert os.environ["BROWSER_CDP"] == "http://global:9222"


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
