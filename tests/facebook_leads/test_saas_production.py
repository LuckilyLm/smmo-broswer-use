from __future__ import annotations

import pytest
import asyncio
import os
from pathlib import Path
from fastapi.testclient import TestClient
from datetime import timedelta

from src.facebook_leads.saas.config import ProductionConfig
from src.facebook_leads.saas.api import create_app
from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage
from src.facebook_leads.saas.db import utc_now
from src.facebook_leads.saas.worker import ExecutionWorker
from scripts.saas_cleanup_artifacts import cleanup
from scripts.saas_seed_demo import main as seed_demo_main


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ENV = {
    "SAAS_ENV": "production",
    "SESSION_SECRET": "production-secret-that-is-at-least-32-characters",
    "SAAS_ALLOWED_ORIGINS": "https://leads.example.com",
    "DATABASE_URL": "postgresql+psycopg://saas:secret@localhost:5432/saas",
}


def test_production_config_reports_browser_use_runtime_capabilities(monkeypatch):
    monkeypatch.setattr("src.facebook_leads.saas.config.platform.system", lambda: "Linux")
    config = ProductionConfig.from_env(
        {**PRODUCTION_ENV, "SAAS_DEPLOYMENT_MODE": "browser-use", "SAAS_RUNTIME_HOST": "local"}
    )

    assert config.runtime_capabilities() == {
        "runtime_host": "local",
        "runtime_available": True,
        "browser_platform": "Linux",
        "local_browser_supported": True,
        "browser_backend": "browser-use",
        "browser_headless": True,
        "browser_cdp_base_url": "http://127.0.0.1",
    }


def test_production_config_reports_remote_browser_runtime_capabilities(monkeypatch):
    monkeypatch.setattr("src.facebook_leads.saas.config.platform.system", lambda: "Linux")
    config = ProductionConfig.from_env(
        {**PRODUCTION_ENV, "SAAS_DEPLOYMENT_MODE": "browser-use", "SAAS_RUNTIME_HOST": "remote"}
    )

    assert config.runtime_available is True
    assert config.browser_cdp_base_url == "http://saas-browser-runtime"
    assert config.browser_runtime_control_url == "http://saas-browser-runtime:8001"
    assert config.runtime_capabilities()["runtime_host"] == "remote"
    assert config.runtime_capabilities()["runtime_available"] is True


def test_production_config_reports_linux_control_plane_only_capabilities(monkeypatch):
    monkeypatch.setattr("src.facebook_leads.saas.config.platform.system", lambda: "Linux")
    config = ProductionConfig.from_env(
        {**PRODUCTION_ENV, "SAAS_DEPLOYMENT_MODE": "control-plane-only", "SAAS_RUNTIME_HOST": "local"}
    )

    assert config.runtime_capabilities() == {
        "runtime_host": "local",
        "runtime_available": False,
        "browser_platform": "Linux",
        "local_browser_supported": True,
        "browser_backend": "browser-use",
        "browser_headless": True,
        "browser_cdp_base_url": "http://127.0.0.1",
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


def test_deployment_uses_only_the_nginx_template():
    assert (REPO_ROOT / "deploy/nginx/saas.conf.template").is_file()
    assert not (REPO_ROOT / "deploy/nginx/saas.conf").exists()


def test_saas_compose_requires_pre_encoded_container_database_url():
    compose = (REPO_ROOT / "docker-compose.saas.prod.yml").read_text(encoding="utf-8")

    assert "DATABASE_URL: ${SAAS_DATABASE_URL:?SAAS_DATABASE_URL is required}" in compose
    assert "postgresql+psycopg://${POSTGRES_USER" not in compose
    assert "${POSTGRES_PASSWORD" not in compose.split("DATABASE_URL:", 1)[1].splitlines()[0]


def test_saas_environment_example_defines_encoded_container_database_url():
    values = dict(
        line.split("=", 1)
        for line in (REPO_ROOT / ".env.production.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    assert values["SAAS_DATABASE_URL"] == "postgresql+psycopg://saas_user:replace-with-a-strong-password@postgres:5432/facebook_leads_saas"


def test_nginx_has_only_the_runtime_template_source_of_truth():
    assert (REPO_ROOT / "deploy/nginx/saas.conf.template").is_file()
    assert not (REPO_ROOT / "deploy/nginx/saas.conf").exists()


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


def test_system_dependencies_include_remote_browser_runtime_control_status(tmp_path, monkeypatch):
    import src.facebook_leads.saas.routers.system as system_router

    service = SaaSService(SaaSStorage(tmp_path / "dependencies.sqlite"))
    tenant = service.create_tenant("Dependencies", "dependencies")
    user = service.create_user("dependencies@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    token = service.login("dependencies@example.com", "pass123456")["access_token"]

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    requested: list[str] = []

    def fake_urlopen(url: str, timeout: int):
        requested.append(f"{url}|{timeout}")
        return Response()

    monkeypatch.setattr(system_router, "urlopen", fake_urlopen)
    config = ProductionConfig.from_env(
        {**PRODUCTION_ENV, "SAAS_DEPLOYMENT_MODE": "browser-use", "SAAS_RUNTIME_HOST": "remote"}
    )

    response = TestClient(create_app(service=service, config=config)).get(
        "/api/system/dependencies",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert runtime["runtime_host"] == "remote"
    assert runtime["browser_cdp_base_url"] == "http://saas-browser-runtime"
    assert runtime["browser_runtime_control_url"] == "http://saas-browser-runtime:8001"
    assert runtime["browser_runtime_control_reachable"] is True
    assert runtime["browser_runtime_control_status"] == "ok"
    assert requested == ["http://saas-browser-runtime:8001/health|2"]


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


def test_create_app_injects_production_runtime_config(tmp_path):
    database = tmp_path / "configured.sqlite"
    SaaSStorage(database)
    profile_root = tmp_path / "custom-profiles"
    config = ProductionConfig.from_env(
        {
            "SAAS_BROWSER_PROFILE_ROOT": str(profile_root),
            "SAAS_BROWSER_CDP_PORT_START": "9500",
            "SAAS_BROWSER_CDP_PORT_END": "9510",
            "SAAS_MAX_QUEUED_EXECUTIONS_PER_TENANT": "7",
        }
    )

    app = create_app(database_url=str(database), config=config)
    service = app.state.service

    assert service.runtime_registry.profiles_root == profile_root
    assert service.runtime_registry.cdp_port_start == 9500
    assert service.runtime_registry.cdp_port_end == 9510
    assert service.max_queued_executions_per_tenant == 7


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
