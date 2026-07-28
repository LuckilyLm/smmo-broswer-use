from __future__ import annotations

import sys
from types import SimpleNamespace

from src.facebook_leads.saas.artifact_bundle import ArtifactObjectConfig, upload_execution_artifacts, write_execution_bundle
from src.facebook_leads.saas.config import ProductionConfig


PRODUCTION_ENV = {
    "SAAS_ENV": "production",
    "SESSION_SECRET": "production-secret-that-is-at-least-32-characters",
    "SAAS_ALLOWED_ORIGINS": "https://leads.example.com",
    "DATABASE_URL": "postgresql+psycopg://saas:secret@postgres:5432/saas",
}


def test_production_config_reads_llm_and_artifact_object_storage(monkeypatch):
    monkeypatch.setattr("src.facebook_leads.saas.config.platform.system", lambda: "Linux")

    config = ProductionConfig.from_env(
        {
            **PRODUCTION_ENV,
            "SAAS_LLM_ENDPOINT": "https://llm.example/v1",
            "SAAS_LLM_MODEL": "gpt-test",
            "OPENAI_API_KEY": "secret",
            "SAAS_ARTIFACT_S3_ENABLED": "true",
            "SAAS_ARTIFACT_S3_ENDPOINT": "http://minio:9000",
            "SAAS_ARTIFACT_S3_ACCESS_KEY": "access",
            "SAAS_ARTIFACT_S3_SECRET_KEY": "secret",
            "SAAS_ARTIFACT_S3_BUCKET": "reports",
            "SAAS_ARTIFACT_S3_PUBLIC_BASE_URL": "https://cdn.example/reports",
            "SAAS_ARTIFACT_S3_SECURE": "false",
        }
    )

    assert config.llm_endpoint == "https://llm.example/v1"
    assert config.llm_api_key == "secret"
    assert config.llm_model == "gpt-test"
    assert config.artifact_s3_enabled is True
    assert config.artifact_s3_endpoint == "http://minio:9000"
    assert config.artifact_s3_bucket == "reports"
    assert config.artifact_s3_secure is False


def test_write_execution_bundle_creates_single_html_and_json_report(tmp_path):
    root = tmp_path / "execution"
    run_dir = root / "runs" / "run_1"
    run_dir.mkdir(parents=True)
    (run_dir / "scan_result.json").write_text(
        '{"keyword":"steel supplier","status":"completed","login_state":"logged_in","contents":[{"url":"https://facebook.example/post"}],"comments":[{"text":"price?"}]}',
        encoding="utf-8",
    )
    (run_dir / "lead_report.json").write_text('{"keyword":"steel supplier","contents":[]}', encoding="utf-8")
    (run_dir / "batch_reply_plan.json").write_text('{"summary":{"eligible_count":0}}', encoding="utf-8")

    paths = write_execution_bundle(
        root,
        tenant_id="tenant_1",
        execution={"id": "exec_1", "status": "completed", "send_disabled": True},
        keywords=[{"keyword": "steel supplier", "status": "completed", "discovered_contents": 1, "scanned_comments": 1}],
        leads=[],
    )

    assert paths["execution_report_json"].exists()
    assert paths["execution_report_html"].exists()
    assert "steel supplier" in paths["execution_report_html"].read_text(encoding="utf-8")


def test_upload_execution_artifacts_disabled_without_configuration(tmp_path):
    result = upload_execution_artifacts(
        tmp_path,
        tenant_id="tenant_1",
        execution_id="exec_1",
        config=ArtifactObjectConfig(
            enabled=False,
            endpoint=None,
            access_key=None,
            secret_key=None,
            bucket=None,
            region="us-east-1",
            prefix="saas-artifacts",
            public_base_url=None,
            secure=True,
        ),
    )

    assert result == {"enabled": False, "uploaded": 0, "items": [], "error": None}


def test_upload_execution_artifacts_uploads_only_html_report(tmp_path, monkeypatch):
    root = tmp_path / "execution"
    root.mkdir()
    (root / "execution_report.html").write_text("<html>report</html>", encoding="utf-8")
    (root / "execution_report.json").write_text('{"internal":true}', encoding="utf-8")
    (root / "worker.log").write_text("debug", encoding="utf-8")
    screenshots = root / "runs" / "run_1"
    screenshots.mkdir(parents=True)
    (screenshots / "screen.png").write_bytes(b"png")

    uploads: list[dict[str, object]] = []

    class FakeClient:
        def upload_file(self, filename, bucket, key, ExtraArgs=None):
            uploads.append({"filename": filename, "bucket": bucket, "key": key, "extra": ExtraArgs})

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *args, **kwargs: FakeClient()))
    monkeypatch.setitem(sys.modules, "botocore", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "botocore.client", SimpleNamespace(Config=lambda *args, **kwargs: {"args": args, "kwargs": kwargs}))

    result = upload_execution_artifacts(
        root,
        tenant_id="tenant_1",
        execution_id="exec_1",
        config=ArtifactObjectConfig(
            enabled=True,
            endpoint="http://minio:9000",
            access_key="access",
            secret_key="secret",
            bucket="reports",
            region="us-east-1",
            prefix="saas-artifacts",
            public_base_url="https://cdn.example/reports",
            secure=False,
        ),
    )

    assert result["uploaded"] == 1
    assert [item["name"] for item in result["items"]] == ["execution_report.html"]
    assert [upload["key"] for upload in uploads] == ["saas-artifacts/tenants/tenant_1/executions/exec_1/execution_report.html"]
    assert (root / "artifact_manifest.json").exists()
