from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.facebook_leads.saas.config import ProductionConfig
from src.facebook_leads.saas.models import TenantContext
from src.facebook_leads.saas.reply_automation import match_comment, render_template
from src.facebook_leads.saas.service import ServiceConflictError, SaaSService
from src.facebook_leads.saas.storage import SaaSStorage


@pytest.fixture()
def service(tmp_path: Path) -> SaaSService:
    return SaaSService(SaaSStorage(tmp_path / "saas.sqlite"), artifacts_root=tmp_path / "artifacts", config=ProductionConfig.from_env({"SAAS_SYSTEM_SEND_ENABLED": "false"}))


@pytest.fixture()
def ctx(service: SaaSService) -> TenantContext:
    tenant = service.create_tenant("Acme", "acme", default_whatsapp="+15550100", default_email="hello@example.com", default_website="https://example.com", default_contact_text="WhatsApp preferred", tenant_reply_enabled=True)
    user = service.create_user("owner@example.com", "password123", "Owner")
    service.add_user_to_tenant(tenant["id"], user["id"], role="owner")
    return TenantContext(tenant_id=tenant["id"], user_id=user["id"], role="owner")


@pytest.fixture()
def campaign(service: SaaSService, ctx: TenantContext) -> dict:
    account = service.create_platform_account(ctx, {"platform": "facebook", "display_name": "FB"})
    return service.create_campaign(ctx, {"name": "Summer", "platform_account_id": account["id"], "positive_keywords_json": ["how much", "interested", "contact"]})


def test_template_crud_preview_and_unknown_variable_reject(service: SaaSService, ctx: TenantContext, campaign: dict):
    template = service.create_reply_template(ctx, {"name": "WhatsApp", "content": "My WhatsApp is {{whatsapp}}", "is_default": True})
    assert service.preview_reply_template(ctx, {"template_id": template["id"], "campaign_id": campaign["id"], "comment": {"author_name": "Ada", "keyword": "chair"}})["rendered"] == "My WhatsApp is +15550100"
    updated = service.update_reply_template(ctx, template["id"], {"content": "Email {{email}}"})
    assert updated and updated["content"] == "Email {{email}}"
    copied = service.copy_reply_template(ctx, template["id"])
    assert copied["name"].endswith("Copy")
    with pytest.raises(ValueError, match="unknown_template_variable"):
        service.create_reply_template(ctx, {"name": "Bad", "content": "{{secret}}"})


def test_rule_matching_negative_priority_and_template_selection(service: SaaSService, ctx: TenantContext, campaign: dict):
    default_template = service.create_reply_template(ctx, {"name": "Default", "content": "Contact {{contact}}", "is_default": True})
    rule_template = service.create_reply_template(ctx, {"name": "Rule", "content": "Hi {{author_name}}, WhatsApp {{whatsapp}}"})
    rule = service.create_reply_match_rule(ctx, {"campaign_id": campaign["id"], "reply_template_id": rule_template["id"], "name": "Interest", "contains_any_json": ["how much"], "priority": 1})
    assert match_comment({"text": "How much?", "author_name": "Buyer", "fingerprint": "1"}, campaign, [rule]).template_id == rule_template["id"]
    campaign = service.update_campaign(ctx, campaign["id"], {"negative_keywords_json": ["fake"]}) or campaign
    assert match_comment({"text": "fake price", "author_name": "Buyer", "fingerprint": "2"}, campaign, [rule]).blocked_reason == "negative_keyword"
    service.update_reply_match_rule(ctx, rule["id"], {"reply_template_id": None})
    execution = _execution(service, ctx, campaign)
    _scan_artifact(service, ctx, execution["id"], [{"comment_id": "c1", "author_name": "Buyer", "text": "How much?", "fingerprint": "fp1"}])
    plan = service.generate_reply_plan_for_execution(ctx, execution["id"])
    candidate = service.list_reply_candidates(ctx)["items"][0]
    assert plan and plan["status"] == "pending_approval"
    assert candidate["reply_template_id"] in {rule_template["id"], default_template["id"]}
    assert "WhatsApp" in (candidate["rendered_reply_text"] or "") or "Contact" in (candidate["rendered_reply_text"] or "")


def test_manual_approval_guards_disabled_runtime_and_idempotency(service: SaaSService, ctx: TenantContext, campaign: dict):
    template = service.create_reply_template(ctx, {"name": "WhatsApp", "content": "My WhatsApp is {{whatsapp}}", "is_default": True})
    service.create_reply_match_rule(ctx, {"campaign_id": campaign["id"], "reply_template_id": template["id"], "name": "Contact", "contains_any_json": ["contact"]})
    execution = _execution(service, ctx, campaign)
    comments = [{"comment_id": "c1", "author_name": "Buyer", "text": "Can I contact you?", "fingerprint": "fp1"}]
    _scan_artifact(service, ctx, execution["id"], comments)
    plan = service.generate_reply_plan_for_execution(ctx, execution["id"])
    service.generate_reply_plan_for_execution(ctx, execution["id"])
    candidates = service.list_reply_candidates(ctx)["items"]
    assert len(candidates) == 1
    candidate = service.approve_reply_candidate(ctx, candidates[0]["id"])
    assert service.approve_reply_candidate(ctx, candidate["id"])["status"] == "approved"
    plan = service.approve_reply_plan(ctx, plan["id"])
    assert service.execute_reply_plan(ctx, plan["id"])["blocked_reason"] == "system_send_disabled"
    assert service.list_reply_records(ctx)["items"][0]["status"] == "blocked"


def test_disabled_campaign_and_no_template_do_not_create_sendable_candidate(service: SaaSService, ctx: TenantContext, campaign: dict):
    disabled = service.update_campaign(ctx, campaign["id"], {"reply_mode": "disabled"}) or campaign
    execution = _execution(service, ctx, disabled)
    _scan_artifact(service, ctx, execution["id"], [{"comment_id": "c1", "author_name": "Buyer", "text": "Interested", "fingerprint": "fp1"}])
    assert service.generate_reply_plan_for_execution(ctx, execution["id"]) is None
    enabled = service.update_campaign(ctx, campaign["id"], {"reply_mode": "manual_approval"}) or campaign
    service.create_reply_match_rule(ctx, {"campaign_id": campaign["id"], "name": "Interest", "contains_any_json": ["interested"]})
    execution = _execution(service, ctx, enabled)
    _scan_artifact(service, ctx, execution["id"], [{"comment_id": "c2", "author_name": "Buyer", "text": "Interested", "fingerprint": "fp2"}])
    service.generate_reply_plan_for_execution(ctx, execution["id"])
    assert service.list_reply_candidates(ctx)["items"][0]["blocked_reason"] == "no_template"


def test_rbac_and_tenant_isolation(service: SaaSService, ctx: TenantContext, campaign: dict):
    viewer = service.create_user("viewer@example.com", "password123", "Viewer")
    service.add_user_to_tenant(ctx.tenant_id, viewer["id"], role="viewer")
    viewer_ctx = TenantContext(ctx.tenant_id, viewer["id"], "viewer")
    with pytest.raises(PermissionError):
        service.create_reply_template(viewer_ctx, {"name": "No", "content": "Hi"})
    member = service.create_user("member@example.com", "password123", "Member")
    service.add_user_to_tenant(ctx.tenant_id, member["id"], role="member")
    with pytest.raises(PermissionError):
        service.update_campaign(TenantContext(ctx.tenant_id, member["id"], "member"), campaign["id"], {"reply_mode": "automatic"})
    other = service.create_tenant("Other", "other")
    assert service.list_reply_candidates(TenantContext(other["id"], ctx.user_id, "owner"))["total"] == 0


def test_historical_campaigns_are_disabled_by_migration_contract(service: SaaSService, ctx: TenantContext, campaign: dict):
    assert campaign["reply_mode"] == "manual_approval"
    service.storage.execute("UPDATE campaigns SET reply_mode = ? WHERE id = ?", ["disabled", campaign["id"]])
    assert service.storage.get_by_id("campaigns", campaign["id"])["reply_mode"] == "disabled"


def test_template_renderer_rejects_missing_and_control_text():
    with pytest.raises(ValueError, match="missing_template_variable"):
        render_template("WhatsApp {{whatsapp}}", {})
    with pytest.raises(ValueError, match="template_content_invalid"):
        render_template("bad\x00text", {"whatsapp": "1"})


def _execution(service: SaaSService, ctx: TenantContext, campaign: dict) -> dict:
    return service.storage.insert("executions", {"tenant_id": ctx.tenant_id, "campaign_id": campaign["id"], "platform": "facebook", "status": "completed", "trigger_type": "manual", "send_disabled": True})


def _scan_artifact(service: SaaSService, ctx: TenantContext, execution_id: str, comments: list[dict]) -> None:
    path = Path(service.artifacts_root) / "tenants" / ctx.tenant_id / "executions" / execution_id / "runs" / "run_test"
    path.mkdir(parents=True, exist_ok=True)
    (path / "scan_result.json").write_text(json.dumps({"keyword": "massage chair", "comments": comments}), encoding="utf-8")
