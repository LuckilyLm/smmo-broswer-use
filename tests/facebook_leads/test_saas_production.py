from __future__ import annotations

import pytest
import asyncio
import json
import os
import subprocess
import textwrap
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import timedelta

from src.facebook_leads.saas.config import ProductionConfig
from src.facebook_leads.saas.api import create_app
from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage
from src.facebook_leads.saas.db import utc_now
from src.facebook_leads.saas.worker import ExecutionWorker
from src.facebook_leads.saas.runtime import BrowserRuntimeRegistry
from scripts.saas_cleanup_artifacts import cleanup
from scripts.saas_seed_demo import main as seed_demo_main
from scripts.saas_worker import build_worker_service


REPO_ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
PRODUCTION_ENV = {
    "SAAS_ENV": "production",
    "SESSION_SECRET": "production-secret-that-is-at-least-32-characters",
    "SAAS_ALLOWED_ORIGINS": "https://leads.example.com",
    "DATABASE_URL": "postgresql+psycopg://saas:secret@localhost:5432/saas",
}


def test_production_config_reports_windows_local_runtime_capabilities(monkeypatch):
    monkeypatch.setattr("src.facebook_leads.saas.config.platform.system", lambda: "Windows")
    config = ProductionConfig.from_env(
        {**PRODUCTION_ENV, "SAAS_DEPLOYMENT_MODE": "windows-local", "SAAS_RUNTIME_HOST": "local"}
    )

    assert config.runtime_capabilities() == {
        "runtime_host": "local",
        "runtime_available": True,
        "browser_platform": "Windows",
        "local_browser_supported": True,
    }


def test_production_config_reports_linux_control_plane_only_capabilities(monkeypatch):
    monkeypatch.setattr("src.facebook_leads.saas.config.platform.system", lambda: "Linux")
    config = ProductionConfig.from_env(
        {**PRODUCTION_ENV, "SAAS_DEPLOYMENT_MODE": "control-plane-only", "SAAS_RUNTIME_HOST": "local"}
    )

    assert config.runtime_capabilities() == {
        "runtime_host": "local",
        "runtime_available": False,
        "browser_platform": "Linux",
        "local_browser_supported": False,
    }


def test_saas_nginx_template_preserves_proxy_and_spa_configuration():
    template = (REPO_ROOT / "deploy/nginx/saas.conf.template").read_text(encoding="utf-8")

    assert "proxy_pass ${SAAS_API_UPSTREAM};" in template
    assert "resolver 127.0.0.11 valid=10s ipv6=off;" in template
    assert "add_header X-Content-Type-Options nosniff always;" in template
    assert "add_header X-Frame-Options SAMEORIGIN always;" in template
    assert "add_header Referrer-Policy strict-origin-when-cross-origin always;" in template
    assert "proxy_set_header Host $host;" in template
    assert "proxy_set_header X-Real-IP $remote_addr;" in template
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in template
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in template
    assert "proxy_connect_timeout 10s;" in template
    assert "proxy_read_timeout 120s;" in template
    assert "try_files $uri $uri/ /index.html;" in template


def test_saas_frontend_dockerfile_limits_nginx_envsubst_to_api_upstream():
    dockerfile = (REPO_ROOT / "deploy/docker/Dockerfile.saas-frontend").read_text(encoding="utf-8")

    assert "ENV NGINX_ENVSUBST_FILTER=^SAAS_API_UPSTREAM$" in dockerfile


def test_saas_frontend_dockerfile_uses_nginx_entrypoint_template():
    dockerfile = (REPO_ROOT / "deploy/docker/Dockerfile.saas-frontend").read_text(encoding="utf-8")

    assert "ENV SAAS_API_UPSTREAM=http://saas-api:8000" in dockerfile
    assert "COPY deploy/nginx/saas.conf.template /etc/nginx/templates/default.conf.template" in dockerfile
    assert "/etc/nginx/conf.d/default.conf" not in dockerfile


def test_production_compose_requires_credentials_and_secrets():
    compose = (REPO_ROOT / "docker-compose.saas.prod.yml").read_text(encoding="utf-8")

    required_expansions = {
        "POSTGRES_DB": "${POSTGRES_DB:?POSTGRES_DB is required}",
        "POSTGRES_USER": "${POSTGRES_USER:?POSTGRES_USER is required}",
        "POSTGRES_PASSWORD": "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}",
        "SAAS_DATABASE_URL": "${SAAS_DATABASE_URL:?SAAS_DATABASE_URL is required}",
        "SESSION_SECRET": "${SESSION_SECRET:?SESSION_SECRET is required}",
        "SAAS_ALLOWED_ORIGINS": "${SAAS_ALLOWED_ORIGINS:?SAAS_ALLOWED_ORIGINS is required}",
    }
    for expansion in required_expansions.values():
        assert expansion in compose
    assert "DATABASE_URL: postgresql+psycopg://${POSTGRES_USER" not in compose


def test_windows_local_compose_requires_credentials_and_secrets():
    compose = (REPO_ROOT / "docker-compose.saas.windows-local.yml").read_text(encoding="utf-8")

    required_expansions = {
        "POSTGRES_DB": "${POSTGRES_DB:?POSTGRES_DB is required}",
        "POSTGRES_USER": "${POSTGRES_USER:?POSTGRES_USER is required}",
        "POSTGRES_PASSWORD": "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}",
        "SAAS_DATABASE_URL": "${SAAS_DATABASE_URL:?SAAS_DATABASE_URL is required}",
        "SESSION_SECRET": "${SESSION_SECRET:?SESSION_SECRET is required}",
        "SAAS_ALLOWED_ORIGINS": "${SAAS_ALLOWED_ORIGINS:?SAAS_ALLOWED_ORIGINS is required}",
    }
    for expansion in required_expansions.values():
        assert expansion in compose
    assert "DATABASE_URL: postgresql+psycopg://${POSTGRES_USER" not in compose


def test_deployment_uses_only_the_nginx_template():
    assert (REPO_ROOT / "deploy/nginx/saas.conf.template").is_file()
    assert not (REPO_ROOT / "deploy/nginx/saas.conf").exists()


def test_windows_local_documentation_starts_declared_migration_service_once():
    guide = (REPO_ROOT / "docs/windows-local-deployment.md").read_text(encoding="utf-8")

    assert "up --build -d postgres saas-migrate frontend" in guide
    assert "run --rm saas-migrate" not in guide
    assert "SAAS_DATABASE_URL" in guide
    assert "matching `DATABASE_URL`" not in guide


@pytest.mark.parametrize("compose_name", ["docker-compose.saas.prod.yml", "docker-compose.saas.windows-local.yml"])
def test_saas_compose_requires_pre_encoded_container_database_url(compose_name):
    compose = (REPO_ROOT / compose_name).read_text(encoding="utf-8")

    assert "DATABASE_URL: ${SAAS_DATABASE_URL:?SAAS_DATABASE_URL is required}" in compose
    assert "postgresql+psycopg://${POSTGRES_USER" not in compose
    assert "${POSTGRES_PASSWORD" not in compose.split("DATABASE_URL:", 1)[1].splitlines()[0]


def test_saas_compose_files_keep_shared_environment_contract_in_parity():
    production = (REPO_ROOT / "docker-compose.saas.prod.yml").read_text(encoding="utf-8")
    windows_local = (REPO_ROOT / "docker-compose.saas.windows-local.yml").read_text(encoding="utf-8")

    def environment_names(compose: str) -> set[str]:
        block = compose.split("x-saas-env: &saas-env\n", 1)[1].split("\nx-logging:", 1)[0]
        return {line.strip().split(":", 1)[0] for line in block.splitlines() if line.startswith("  ")}

    assert environment_names(production) == environment_names(windows_local)


@pytest.mark.parametrize("example_name", [".env.production.example", ".env.windows-local.example"])
def test_saas_environment_examples_define_encoded_container_database_url(example_name):
    values = dict(
        line.split("=", 1)
        for line in (REPO_ROOT / example_name).read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    assert values["SAAS_DATABASE_URL"] == "postgresql+psycopg://saas_user:replace-with-a-strong-password@postgres:5432/facebook_leads_saas"


def test_windows_local_deployment_uses_compose_single_migration_sequence_and_externally_reachable_api():
    guide = (REPO_ROOT / "docs/windows-local-deployment.md").read_text(encoding="utf-8")

    assert "docker compose --env-file .env.windows-local -f docker-compose.saas.windows-local.yml up --build -d postgres saas-migrate frontend" in guide
    assert "docker compose --env-file .env.windows-local -f docker-compose.saas.windows-local.yml run --rm saas-migrate" not in guide
    assert "binds Uvicorn to `0.0.0.0:8000`" in guide
    assert "host.docker.internal:8000" in guide


def test_nginx_has_only_the_runtime_template_source_of_truth():
    assert (REPO_ROOT / "deploy/nginx/saas.conf.template").is_file()
    assert not (REPO_ROOT / "deploy/nginx/saas.conf").exists()


def test_windows_local_compose_contains_only_host_api_deployment_services():
    compose = (REPO_ROOT / "docker-compose.saas.windows-local.yml").read_text(encoding="utf-8")

    services = compose.split("services:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    service_lines = {
        line.strip()[:-1]
        for line in services.splitlines()
        if line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":")
    }
    assert service_lines == {"postgres", "saas-migrate", "frontend"}
    assert '"127.0.0.1:5432:5432"' in compose
    assert '"127.0.0.1:${SAAS_FRONTEND_PORT:-8080}:80"' in compose
    assert "SAAS_API_UPSTREAM: ${SAAS_API_UPSTREAM:-http://host.docker.internal:8000}" in compose
    assert "host.docker.internal:host-gateway" in compose
    assert "saas_postgres_data:/var/lib/postgresql/data" in compose
    assert "saas-migrate:" in compose
    assert "condition: service_completed_successfully" in compose
    assert "saas-api" not in service_lines
    assert "saas-worker" not in service_lines


def test_production_config_requires_session_secret(monkeypatch):
    monkeypatch.setenv("SAAS_ENV", "production")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.setenv("SAAS_ALLOWED_ORIGINS", "https://leads.example.com")

    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        ProductionConfig.from_env()


def test_production_config_rejects_cors_wildcard_with_credentials(monkeypatch):
    monkeypatch.setenv("SAAS_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "production-secret-that-is-at-least-32-characters")
    monkeypatch.setenv("SAAS_ALLOWED_ORIGINS", "*")

    with pytest.raises(RuntimeError, match="wildcard"):
        ProductionConfig.from_env()


def test_health_is_a_liveness_check_even_when_database_is_down(tmp_path, monkeypatch):
    service = SaaSService(SaaSStorage(tmp_path / "production.sqlite"))
    monkeypatch.setattr(service.storage, "ping", lambda: (_ for _ in ()).throw(RuntimeError("database details")))
    app = create_app(service=service, config=ProductionConfig.from_env({}))

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_endpoint_returns_only_public_build_metadata(tmp_path):
    service = SaaSService(SaaSStorage(tmp_path / "production.sqlite"))
    config = ProductionConfig.from_env({"APP_VERSION": "7.4.0", "GIT_COMMIT": "abc1234", "BUILD_TIME": "2026-07-22T12:00:00Z"})

    response = TestClient(create_app(service=service, config=config)).get("/api/version")

    assert response.status_code == 200
    assert response.json() == {"app_version": "7.4.0", "git_commit": "abc1234", "build_time": "2026-07-22T12:00:00Z"}


def test_api_errors_use_safe_stable_envelope(tmp_path):
    service = SaaSService(SaaSStorage(tmp_path / "production.sqlite"))
    tenant = service.create_tenant("Production", "production")
    user = service.create_user("admin@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    token = service.login("admin@example.com", "pass123456")["access_token"]
    client = TestClient(create_app(service=service, config=ProductionConfig.from_env({})))

    response = client.get("/api/executions/missing", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "not found"}}


def test_session_cookie_is_signed_and_tampering_is_rejected(tmp_path):
    service = SaaSService(SaaSStorage(tmp_path / "production.sqlite"))
    tenant = service.create_tenant("Production", "production")
    user = service.create_user("admin@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    config = ProductionConfig.from_env({"SESSION_SECRET": "test-secret-that-is-long-enough-for-signing"})
    client = TestClient(create_app(service=service, config=config))

    login = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "pass123456"})
    raw_token = login.json()["access_token"]
    cookie = client.cookies.get("leadflow_session")

    assert cookie and cookie != raw_token and cookie.startswith(f"{raw_token}.")
    client.cookies.set("leadflow_session", f"{cookie}tampered")
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "session_expired"


def test_login_rate_limit_blocks_sixth_failed_attempt(tmp_path):
    service = SaaSService(SaaSStorage(tmp_path / "production.sqlite"))
    client = TestClient(create_app(service=service, config=ProductionConfig.from_env({})))

    for _attempt in range(5):
        assert client.post("/api/auth/login", json={"email": "missing@example.com", "password": "wrong"}).status_code == 401

    blocked = client.post("/api/auth/login", json={"email": "missing@example.com", "password": "wrong"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limit_reached"


def test_worker_and_scheduler_status_use_fresh_heartbeats(tmp_path):
    service = SaaSService(SaaSStorage(tmp_path / "production.sqlite"))
    tenant = service.create_tenant("Production", "production")
    user = service.create_user("admin@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    token = service.login("admin@example.com", "pass123456")["access_token"]
    now = utc_now()
    service.storage.insert("worker_heartbeats", {"worker_id": "worker-fresh", "last_seen_at": now, "status": "online"})
    service.storage.insert("worker_heartbeats", {"worker_id": "worker-stale", "last_seen_at": now - timedelta(minutes=5), "status": "online"})
    service.storage.insert("worker_heartbeats", {"worker_id": "scheduler", "last_seen_at": now, "status": "online", "last_error": None})
    client = TestClient(create_app(service=service, config=ProductionConfig.from_env({"SAAS_HEARTBEAT_STALE_SECONDS": "60"})))
    headers = {"Authorization": f"Bearer {token}"}

    worker = client.get("/api/system/worker-status", headers=headers).json()
    scheduler = client.get("/api/system/scheduler-status", headers=headers).json()

    assert worker == {"online": True, "last_heartbeat_at": worker["last_heartbeat_at"], "worker_count": 1}
    assert scheduler["online"] is True
    assert scheduler["last_tick_at"]
    assert scheduler["due_campaign_count"] == 0
    assert scheduler["last_error"] is None


def test_stopped_worker_and_failed_scheduler_are_offline(tmp_path):
    service = SaaSService(SaaSStorage(tmp_path / "production.sqlite"))
    tenant = service.create_tenant("Production", "production")
    user = service.create_user("admin@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    token = service.login("admin@example.com", "pass123456")["access_token"]
    now = utc_now()
    service.storage.insert("worker_heartbeats", {"worker_id": "worker-stopped", "last_seen_at": now, "status": "stopped"})
    service.storage.insert("worker_heartbeats", {"worker_id": "scheduler", "last_seen_at": now, "status": "error", "last_error": "DatabaseError"})
    client = TestClient(create_app(service=service, config=ProductionConfig.from_env({})))
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/system/worker-status", headers=headers).json()["online"] is False
    scheduler = client.get("/api/system/scheduler-status", headers=headers).json()
    assert scheduler["online"] is False
    assert scheduler["last_error"] == "DatabaseError"


def test_queue_backpressure_rejects_manual_run_with_clear_code(tmp_path):
    storage = SaaSStorage(tmp_path / "production.sqlite")
    service = SaaSService(storage, max_queued_executions_per_tenant=1)
    tenant = service.create_tenant("Production", "production")
    user = service.create_user("admin@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    context = service.context_from_token(service.login("admin@example.com", "pass123456")["access_token"])
    account = service.create_platform_account(context, {"platform": "facebook", "display_name": "Page"})
    campaign = service.create_campaign(context, {"name": "Campaign", "platform_account_id": account["id"]})
    service.create_keyword(context, campaign["id"], {"keyword": "massage chair"})

    first = service.enqueue_campaign_execution(context, campaign["id"], trigger_type="manual")

    assert first["status"] == "queued"
    with pytest.raises(ValueError, match="queue_limit_reached"):
        service.enqueue_campaign_execution(context, campaign["id"], trigger_type="manual")


def test_queue_limit_api_error_uses_stable_code(tmp_path, monkeypatch):
    service = SaaSService(SaaSStorage(tmp_path / "queue-error.sqlite"))
    tenant = service.create_tenant("Queue", "queue")
    user = service.create_user("queue@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    token = service.login("queue@example.com", "pass123456")["access_token"]

    async def queue_full(*_args, **_kwargs):
        raise ValueError("queue_limit_reached")

    monkeypatch.setattr(service, "run_campaign", queue_full)
    response = TestClient(create_app(service=service)).post(
        "/api/campaigns/campaign/run",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == {"code": "queue_limit_reached", "message": "queue_limit_reached"}


def test_worker_graceful_shutdown_does_not_claim_new_work(tmp_path):
    storage = SaaSStorage(tmp_path / "production.sqlite")
    service = SaaSService(storage)
    tenant = service.create_tenant("Production", "production")
    user = service.create_user("admin@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    context = service.context_from_token(service.login("admin@example.com", "pass123456")["access_token"])
    account = service.create_platform_account(context, {"platform": "facebook", "display_name": "Page"})
    campaign = service.create_campaign(context, {"name": "Campaign", "platform_account_id": account["id"]})
    service.create_keyword(context, campaign["id"], {"keyword": "massage chair"})
    queued = service.enqueue_campaign_execution(context, campaign["id"], trigger_type="manual")
    stop_event = asyncio.Event()
    stop_event.set()

    asyncio.run(ExecutionWorker(service, worker_id="graceful-worker").run_forever(poll_seconds=0.01, stop_event=stop_event))

    queue = service.storage.find_one("execution_queue_items", {"execution_id": queued["id"]})
    assert queue["status"] == "queued"


def test_stale_recovery_preserves_work_owned_by_worker_with_fresh_heartbeat(tmp_path):
    storage = SaaSStorage(tmp_path / "production.sqlite")
    service = SaaSService(storage)
    tenant = service.create_tenant("Production", "production")
    user = service.create_user("admin@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    context = service.context_from_token(service.login("admin@example.com", "pass123456")["access_token"])
    account = service.create_platform_account(context, {"platform": "facebook", "display_name": "Page"})
    campaign = service.create_campaign(context, {"name": "Campaign", "platform_account_id": account["id"]})
    service.create_keyword(context, campaign["id"], {"keyword": "massage chair"})
    execution = service.enqueue_campaign_execution(context, campaign["id"], trigger_type="manual")
    item = storage.claim_queue_item(worker_id="worker-live")
    old = utc_now() - timedelta(hours=8)
    storage.update_by_id("execution_queue_items", item["id"], {"started_at": old})
    heartbeat = storage.insert(
        "worker_heartbeats",
        {"worker_id": "worker-live", "last_seen_at": utc_now(), "status": "running", "current_queue_item_id": item["id"]},
    )

    assert storage.fail_stale_queue_items(
        stale_before=utc_now() - timedelta(hours=6), heartbeat_stale_before=utc_now() - timedelta(minutes=1)
    ) == 0
    storage.update_by_id("worker_heartbeats", heartbeat["id"], {"last_seen_at": old})
    assert storage.fail_stale_queue_items(
        stale_before=utc_now() - timedelta(hours=6), heartbeat_stale_before=utc_now() - timedelta(minutes=1)
    ) == 1
    assert storage.find_one("execution_queue_items", {"execution_id": execution["id"]})["status"] == "failed"


def test_artifact_cleanup_is_dry_run_by_default_and_execute_is_explicit(tmp_path):
    execution_dir = tmp_path / "tenants" / "tenant-1" / "executions" / "execution-1"
    execution_dir.mkdir(parents=True)
    marker = execution_dir / "result.json"
    marker.write_text("{}", encoding="utf-8")
    old = (utc_now() - timedelta(days=40)).timestamp()
    os.utime(execution_dir, (old, old))

    assert cleanup(tmp_path, retention_days=30) == [execution_dir.resolve()]
    assert marker.exists()
    cleanup(tmp_path, retention_days=30, execute=True)
    assert not execution_dir.exists()


def test_bootstrap_admin_only_runs_on_empty_database(tmp_path):
    service = SaaSService(SaaSStorage(tmp_path / "production.sqlite"))

    created = service.bootstrap_admin("bootstrap@example.com", "long-temporary-password")
    ignored = service.bootstrap_admin("second@example.com", "another-password")

    assert created and created["must_change_password"] is True
    assert ignored is None
    assert service.storage.count("users") == 1


def test_demo_seed_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SAAS_ENABLE_DEMO_SEED", raising=False)
    monkeypatch.setattr("sys.argv", ["saas_seed_demo.py"])

    with pytest.raises(SystemExit, match="Demo seed is disabled"):
        seed_demo_main()


def test_ready_requires_current_schema(tmp_path, monkeypatch):
    service = SaaSService(SaaSStorage(tmp_path / "production.sqlite"))
    monkeypatch.setattr(service.storage, "schema_current", lambda: False)

    response = TestClient(create_app(service=service, config=ProductionConfig.from_env({}))).get("/api/ready")

    assert response.status_code == 503
    assert response.json()["error"] == {"code": "service_unavailable", "message": "Request failed"}


def test_windows_agent_api_does_not_reconcile_host_pids(tmp_path, monkeypatch):
    service = SaaSService(SaaSStorage(tmp_path / "production.sqlite"))
    monkeypatch.setattr(
        service.runtime_registry,
        "reconcile_all",
        lambda: (_ for _ in ()).throw(AssertionError("container must not inspect Windows PIDs")),
    )
    config = ProductionConfig.from_env({"SAAS_RUNTIME_HOST": "windows-agent"})

    with TestClient(create_app(service=service, config=config)) as client:
        assert client.get("/api/health").status_code == 200


def test_create_app_injects_production_runtime_config(tmp_path):
    database = tmp_path / "configured.sqlite"
    SaaSStorage(database)
    profile_root = tmp_path / "custom-profiles"
    config = ProductionConfig.from_env(
        {
            "SAAS_BROWSER_PROFILE_ROOT": str(profile_root),
            "SAAS_BROWSER_CDP_PORT_START": "9500",
            "SAAS_BROWSER_CDP_PORT_END": "9510",
            "SAAS_CHROME_EXECUTABLE": str(tmp_path / "chrome.exe"),
            "SAAS_MAX_QUEUED_EXECUTIONS_PER_TENANT": "7",
        }
    )

    app = create_app(database_url=str(database), config=config)
    service = app.state.service

    assert service.runtime_registry.profiles_root == profile_root
    assert service.runtime_registry.cdp_port_start == 9500
    assert service.runtime_registry.cdp_port_end == 9510
    assert service.runtime_registry.chrome_executable == str(tmp_path / "chrome.exe")
    assert service.max_queued_executions_per_tenant == 7


def test_windows_agent_runtime_operations_fail_explicitly(tmp_path):
    storage = SaaSStorage(tmp_path / "agent.sqlite")
    registry = BrowserRuntimeRegistry(storage, runtime_host="windows-agent")
    service = SaaSService(storage, runtime_registry=registry)
    tenant = service.create_tenant("Agent", "agent")
    user = service.create_user("agent@example.com", "pass123456", "Agent")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    context = service.context_from_token(service.login("agent@example.com", "pass123456")["access_token"])
    account = service.create_platform_account(context, {"platform": "facebook", "display_name": "Page"})
    client = TestClient(create_app(service=service, config=ProductionConfig.from_env({"SAAS_RUNTIME_HOST": "windows-agent"})))

    response = client.post(f"/api/platform-accounts/{account['id']}/connect", headers={"Authorization": f"Bearer {service.login('agent@example.com', 'pass123456')['access_token']}"})

    assert response.status_code == 501
    assert response.json()["error"] == {
        "code": "runtime_host_not_implemented",
        "message": "windows-agent runtime host is not implemented",
    }


def test_windows_agent_worker_fails_instead_of_falling_back_local():
    config = ProductionConfig.from_env({"SAAS_RUNTIME_HOST": "windows-agent"})

    with pytest.raises(RuntimeError, match="windows-agent runtime host is not implemented"):
        build_worker_service(config)


def test_windows_local_environment_example_is_safe_and_complete():
    template = (REPO_ROOT / ".env.windows-local.example").read_text(encoding="utf-8")

    expected = {
        "SAAS_ENV": "production",
        "SAAS_DEPLOYMENT_MODE": "windows-local",
        "SAAS_RUNTIME_HOST": "local",
        "DATABASE_URL": "postgresql+psycopg://saas_user:replace-with-a-strong-password@127.0.0.1:5432/facebook_leads_saas",
        "SAAS_CHROME_EXECUTABLE": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "SAAS_BROWSER_CDP_PORT_START": "9400",
        "SAAS_BROWSER_CDP_PORT_END": "9499",
        "SAAS_ALLOWED_ORIGINS": "http://127.0.0.1:8080",
        "SAAS_COOKIE_SECURE": "false",
        "SESSION_SECRET": "",
        "OPENAI_API_KEY": "",
        "OPENAI_ENDPOINT": "https://api.openai.com/v1",
        "FACEBOOK_LEADS_LLM_MODEL": "gpt-5.5",
    }
    values = dict(
        line.split("=", 1)
        for line in template.splitlines()
        if line and not line.lstrip().startswith("#") and "=" in line
    )
    assert values.items() >= expected.items()
    assert values["SAAS_BROWSER_PROFILE_ROOT"].startswith("C:\\Users\\")


def run_powershell(script: str, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=REPO_ROOT,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        timeout=20,
    )


def quote_powershell(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def test_windows_dotenv_parser_handles_quotes_comments_equals_and_process_overrides(tmp_path):
    env_file = tmp_path / "valid.env"
    env_file.write_text(
        textwrap.dedent(
            '''
            PLAIN=value # comment
            DOUBLE="value # still value = yes" # comment
            SINGLE='single # still = yes' # comment
            EMPTY=""
            OVERRIDE=file-value
            '''
        ).strip(),
        encoding="utf-8",
    )
    common = quote_powershell(REPO_ROOT / "scripts/saas_windows_common.ps1")
    path = quote_powershell(env_file)
    script = (
        f". {common}; Import-SaasEnvironmentFile -Path {path}; "
        "$result = [ordered]@{PLAIN=$env:PLAIN;DOUBLE=$env:DOUBLE;SINGLE=$env:SINGLE;EMPTY=$env:EMPTY;OVERRIDE=$env:OVERRIDE}; "
        "$result | ConvertTo-Json -Compress"
    )

    result = run_powershell(script, env={"OVERRIDE": "process-value"})

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "PLAIN": "value",
        "DOUBLE": "value # still value = yes",
        "SINGLE": "single # still = yes",
        "EMPTY": None,  # Windows PowerShell exposes empty process-environment values as null.
        "OVERRIDE": "process-value",
    }


@pytest.mark.parametrize(
    "entry",
    ["1INVALID=value", "BAD-NAME=value", 'BROKEN="unterminated', "BROKEN='unterminated", "NO_EQUALS"],
)
def test_windows_dotenv_parser_rejects_invalid_entries(tmp_path, entry):
    env_file = tmp_path / "invalid.env"
    env_file.write_text(entry, encoding="utf-8")
    script = (
        f". {quote_powershell(REPO_ROOT / 'scripts/saas_windows_common.ps1')}; "
        f"Import-SaasEnvironmentFile -Path {quote_powershell(env_file)}"
    )

    result = run_powershell(script)

    assert result.returncode != 0
    assert "Invalid environment entry" in result.stderr
    assert entry not in result.stderr


def test_windows_alembic_revision_parser_compares_complete_normalized_sets():
    common = quote_powershell(REPO_ROOT / "scripts/saas_windows_common.ps1")
    script = textwrap.dedent(
        f"""
        . {common}
        $heads = ConvertFrom-SaasAlembicOutput -Output "007_saas_productization (head)`r`nabc123 (head)"
        $current = ConvertFrom-SaasAlembicOutput -Output "abc123`n007_saas_productization"
        $same = Test-SaasRevisionSetsEqual -Expected $heads -Actual $current
        $partial = Test-SaasRevisionSetsEqual -Expected $heads -Actual @("007_saas_productization")
        [ordered]@{{Heads=$heads;Same=$same;Partial=$partial}} | ConvertTo-Json -Compress
        """
    )

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["Heads"] == ["007_saas_productization", "abc123"]
    assert parsed["Same"] is True
    assert parsed["Partial"] is False


def test_windows_alembic_revision_parser_ignores_native_command_diagnostics():
    common = quote_powershell(REPO_ROOT / "scripts/saas_windows_common.ps1")
    script = textwrap.dedent(
        f"""
        . {common}
        $output = @'
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
py.exe : INFO  [alembic.runtime.migration] Will assume transactional DDL.
At C:\\repo\\scripts\\saas_windows_common.ps1:146 char:15
+     $heads = (& $Python -m alembic heads 2>&1 | Out-String).Trim()
+               ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (INFO [alembic...]:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
007_saas_productization (head)
'@
        ConvertFrom-SaasAlembicOutput -Output $output | ConvertTo-Json -Compress
        """
    )

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == "007_saas_productization"


def test_windows_alembic_revision_parser_rejects_empty_current():
    common = quote_powershell(REPO_ROOT / "scripts/saas_windows_common.ps1")
    script = textwrap.dedent(
        f"""
        . {common}
        try {{ Assert-SaasAlembicRevisionSets -HeadsOutput "007_saas_productization (head)" -CurrentOutput "" }}
        catch {{ [Console]::Error.Write($_.Exception.Message); exit 7 }}
        """
    )

    result = run_powershell(script)

    assert result.returncode == 7
    assert "current Alembic revision" in result.stderr


def test_windows_database_target_accepts_only_supported_complete_postgres_urls():
    common = quote_powershell(REPO_ROOT / "scripts/saas_windows_common.ps1")
    script = textwrap.dedent(
        f"""
        . {common}
        $accepted = @()
        foreach ($url in @("postgresql://user:secret@db.example:5433/app", "postgresql+psycopg://user:secret@db.example/app")) {{
            $env:DATABASE_URL = $url
            $target = Get-SaasDatabaseTarget
            $accepted += "$($target.Host):$($target.Port)"
        }}
        $rejected = @()
        foreach ($url in @("mysql://db.example/app", "postgresql:///app", "postgresql://db.example", "postgresql://db.example:0/app", "postgresql://db.example:65536/app", "postgresql://db.example:not-a-port/app")) {{
            $env:DATABASE_URL = $url
            try {{ $null = Get-SaasDatabaseTarget }} catch {{ $rejected += $_.Exception.Message }}
        }}
        [ordered]@{{Accepted=$accepted;Rejected=$rejected}} | ConvertTo-Json -Compress
        """
    )

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["Accepted"] == ["db.example:5433", "db.example:5432"]
    assert len(parsed["Rejected"]) == 6
    assert all("DATABASE_URL" in message for message in parsed["Rejected"])
    assert "secret" not in result.stdout and "secret" not in result.stderr


def test_windows_local_launchers_share_validation_and_exact_commands():
    helper = (REPO_ROOT / "scripts/saas_windows_common.ps1").read_text(encoding="utf-8")
    api = (REPO_ROOT / "scripts/start_saas_api_windows.ps1").read_text(encoding="utf-8")
    worker = (REPO_ROOT / "scripts/start_saas_worker_windows.ps1").read_text(encoding="utf-8")
    scheduler = (REPO_ROOT / "scripts/start_saas_scheduler_windows.ps1").read_text(encoding="utf-8")

    assert "[Environment]::GetEnvironmentVariable($name, 'Process')" in helper
    assert "Test-NetConnection" in helper
    assert "python -m alembic" not in helper  # resolved Python command must be used
    for required in (
        "SAAS_ENV",
        "SAAS_DEPLOYMENT_MODE",
        "SAAS_RUNTIME_HOST",
        "DATABASE_URL",
        "SESSION_SECRET",
        "SAAS_ALLOWED_ORIGINS",
        "SAAS_CHROME_EXECUTABLE",
        "SAAS_BROWSER_PROFILE_ROOT",
    ):
        assert required in helper
    assert "Test-Path -LiteralPath $env:SAAS_CHROME_EXECUTABLE -PathType Leaf" in helper
    assert "--version" in helper
    assert "alembic" in helper and "current" in helper and "heads" in helper
    assert '& $python -m uvicorn "src.facebook_leads.saas.api:app" --host "0.0.0.0" --port "8000" --workers "1"' in api
    assert '"scripts/saas_worker.py"' in worker
    assert '"scripts/saas_scheduler.py"' in scheduler
    for launcher in (api, worker, scheduler):
        assert '[string]$EnvFile = ".env.windows-local"' in launcher
        assert "[switch]$SkipServiceChecks" in launcher
        assert "Initialize-SaasWindowsEnvironment" in launcher
        assert "-SkipServiceChecks:$SkipServiceChecks" in launcher


def test_windows_launcher_terminates_only_the_original_process_tree():
    common = quote_powershell(REPO_ROOT / "scripts/saas_windows_common.ps1")
    script = textwrap.dedent(
        f"""
        . {common}
        function taskkill {{
            param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
            $script:taskkillArguments = @($Arguments)
            $global:LASTEXITCODE = 0
        }}
        $current = Get-Process -Id $PID
        Stop-SaasProcessTree -ProcessId $current.Id -ExpectedStartTime $current.StartTime
        $matched = $script:taskkillArguments
        Remove-Variable -Name taskkillArguments -Scope Script -ErrorAction SilentlyContinue
        Stop-SaasProcessTree -ProcessId $current.Id -ExpectedStartTime $current.StartTime.AddSeconds(1)
        [ordered]@{{Pid=$current.Id;Matched=$matched;Mismatched=$(Get-Variable -Name taskkillArguments -Scope Script -ValueOnly -ErrorAction SilentlyContinue)}} | ConvertTo-Json -Compress
        """
    )

    result = run_powershell(script)

    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["Matched"] == ["/PID", str(parsed["Pid"]), "/T", "/F"]
    assert not parsed["Mismatched"]


def test_unified_windows_launcher_orchestrates_and_reports_truthfully():
    launcher = (REPO_ROOT / "scripts/start_saas_windows.ps1").read_text(encoding="utf-8")

    assert "[switch]$WithScheduler" in launcher
    assert '"start_saas_api_windows.ps1"' in launcher
    assert '"start_saas_worker_windows.ps1"' in launcher
    assert '"start_saas_scheduler_windows.ps1"' in launcher
    assert "Start-Process" in launcher
    assert 'return [pscustomobject]@{ ProcessId = $process.Id; StartTime = $process.StartTime }' in launcher
    assert "Stop-SaasProcessTree -ProcessId $child.ProcessId -ExpectedStartTime $child.StartTime" in launcher
    assert '"-SkipServiceChecks"' in launcher
    assert "Initialize-SaasWindowsEnvironment -EnvFile $EnvFile" in launcher
    assert "$startupSucceeded = $false" in launcher
    assert "finally" in launcher
    assert "if (-not $startupSucceeded)" in launcher
    assert "-NoExit" not in launcher
    assert "Stop-SaasChildren" in launcher
    assert "Test-SaasChildExited -Child $schedulerProcess" in launcher
    assert "/api/health" in launcher
    assert "/api/ready" in launcher
    for label in ("Frontend", "API", "Ready", "PostgreSQL", "Worker", "Runtime"):
        assert f'"{label}' in launcher
    assert "requires login" in launcher.lower()
    assert "available" not in "\n".join(
        line.lower() for line in launcher.splitlines() if "worker" in line.lower() or "runtime" in line.lower()
    )


def test_runtime_error_detail_preserves_code_and_message(tmp_path):
    service = SaaSService(SaaSStorage(tmp_path / "errors.sqlite"))
    tenant = service.create_tenant("Errors", "errors")
    user = service.create_user("errors@example.com", "pass123456", "Errors")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    token = service.login("errors@example.com", "pass123456")["access_token"]
    account = service.create_platform_account(service.context_from_token(token), {"platform": "facebook", "display_name": "Page"})
    service.runtime_registry.create_runtime(service.context_from_token(token), account["id"])
    client = TestClient(create_app(service=service, config=ProductionConfig.from_env({})))

    response = client.post(
        f"/api/platform-accounts/{account['id']}/reset-profile",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirm": "wrong"},
    )

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "confirmation_required",
        "message": "reset profile requires exact confirmation",
    }
