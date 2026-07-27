from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.facebook_leads.saas.api import create_app
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


def test_reply_template_api_rejects_unknown_variables_and_extra_fields(service: SaaSService, ctx: TenantContext):
    client = TestClient(create_app(service=service))
    token = service.login("owner@example.com", "password123")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    unknown = client.post("/api/reply-templates", headers=headers, json={"name": "Bad", "content": "{{secret}}"})
    extra = client.post("/api/reply-templates", headers=headers, json={"name": "Bad", "content": "Hi", "unexpected": True})

    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "invalid_request"
    assert unknown.json()["error"]["fields"][0]["field"] == "content"
    assert extra.status_code == 422
    assert extra.json()["error"]["fields"][0]["field"] == "unexpected"


def test_campaign_and_match_rule_validate_template_associations(service: SaaSService, ctx: TenantContext, campaign: dict):
    template = service.create_reply_template(ctx, {"name": "Valid", "content": "Email {{email}}"})
    assert service.update_campaign(ctx, campaign["id"], {"default_reply_template_id": template["id"]})["default_reply_template_id"] == template["id"]

    with pytest.raises(PermissionError, match="reply template not found"):
        service.update_campaign(ctx, campaign["id"], {"default_reply_template_id": "tpl_missing"})

    other_tenant = service.create_tenant("Other", "other-template")
    other_user = service.create_user("other-template@example.com", "password123", "Other")
    service.add_user_to_tenant(other_tenant["id"], other_user["id"], role="owner")
    other_ctx = TenantContext(other_tenant["id"], other_user["id"], "owner")
    other_template = service.create_reply_template(other_ctx, {"name": "Other", "content": "Email {{email}}"})
    other_account = service.create_platform_account(other_ctx, {"platform": "facebook", "display_name": "Other FB"})
    other_campaign = service.create_campaign(other_ctx, {"name": "Other Campaign", "platform_account_id": other_account["id"]})

    rule = service.create_reply_match_rule(ctx, {"campaign_id": campaign["id"], "reply_template_id": template["id"], "name": "Valid Rule", "contains_any_json": ["price"]})
    with pytest.raises(PermissionError, match="reply template not found"):
        service.update_reply_match_rule(ctx, rule["id"], {"reply_template_id": other_template["id"]})
    with pytest.raises(PermissionError, match="campaign not found"):
        service.update_reply_match_rule(ctx, rule["id"], {"campaign_id": other_campaign["id"]})


def test_reply_match_rule_copy_test_and_regex_validation(service: SaaSService, ctx: TenantContext, campaign: dict):
    template = service.create_reply_template(ctx, {"name": "Rule Template", "content": "Hi {{author_name}}, {{contact}}"})
    rule = service.create_reply_match_rule(ctx, {"campaign_id": campaign["id"], "reply_template_id": template["id"], "name": "Interest", "contains_any_json": ["price"], "regex_pattern": "price|cost"})

    copied = service.copy_reply_match_rule(ctx, rule["id"])
    tested = service.test_reply_match_rule(ctx, {**rule, "comment_text": "What is the price?", "author_name": "Ada"})

    assert copied["name"].endswith("Copy")
    assert copied["enabled"] is False
    assert tested["status"] == "matched"
    assert tested["selected_template_id"] == template["id"]
    with pytest.raises(ValueError, match="invalid_regex"):
        service.create_reply_match_rule(ctx, {"campaign_id": campaign["id"], "name": "Bad Regex", "regex_pattern": "["})


def test_reply_match_rule_api_rejects_invalid_regex_and_extra_fields(service: SaaSService, ctx: TenantContext, campaign: dict):
    client = TestClient(create_app(service=service))
    token = service.login("owner@example.com", "password123")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    invalid = client.post("/api/reply-match-rules", headers=headers, json={"campaign_id": campaign["id"], "name": "Bad Regex", "regex_pattern": "["})
    extra = client.post("/api/reply-match-rules", headers=headers, json={"campaign_id": campaign["id"], "name": "Extra", "unexpected": True})

    assert invalid.status_code == 422
    assert invalid.json()["error"]["fields"][0]["field"] == "regex_pattern"
    assert extra.status_code == 422
    assert extra.json()["error"]["fields"][0]["field"] == "unexpected"


def test_campaign_initial_keywords_are_created_transactionally(service: SaaSService, ctx: TenantContext):
    account = service.create_platform_account(ctx, {"platform": "facebook", "display_name": "Transactional FB"})
    created = service.create_campaign_with_keywords(
        ctx,
        {"name": "Transactional", "platform_account_id": account["id"]},
        [" massage chair ", "Massage Chair", "sofa"],
    )

    assert {row["keyword"] for row in service.list_keywords(ctx, created["id"])} == {"massage chair", "sofa"}

    before = service.storage.count("campaigns", tenant_id=ctx.tenant_id)
    with pytest.raises(ValueError, match="keyword_too_long"):
        service.create_campaign_with_keywords(
            ctx,
            {"name": "Rollback", "platform_account_id": account["id"]},
            ["ok", "x" * 256],
        )
    assert service.storage.count("campaigns", tenant_id=ctx.tenant_id) == before
    assert not service.storage.find_one("campaigns", {"tenant_id": ctx.tenant_id, "name": "Rollback"})


def test_bulk_keywords_are_transactional_and_validated(service: SaaSService, ctx: TenantContext):
    account = service.create_platform_account(ctx, {"platform": "facebook", "display_name": "Keywords FB"})
    campaign = service.create_campaign(ctx, {"name": "Keywords", "platform_account_id": account["id"]})

    created = service.create_keywords(ctx, campaign["id"], {"keywords": [" price ", "PRICE", "availability"], "enabled": False, "priority": 7})

    assert created["created"] == 2
    rows = service.list_keywords(ctx, campaign["id"])
    assert {row["keyword"] for row in rows} == {"price", "availability"}
    assert {row["priority"] for row in rows} == {7}
    before = service.storage.count("campaign_keywords", tenant_id=ctx.tenant_id, filters={"campaign_id": campaign["id"]})
    with pytest.raises(ValueError, match="keyword_too_long"):
        service.create_keywords(ctx, campaign["id"], {"keywords": ["valid", "x" * 256], "enabled": False})
    assert service.storage.count("campaign_keywords", tenant_id=ctx.tenant_id, filters={"campaign_id": campaign["id"]}) == before


def test_template_archive_blocks_default_and_in_use_templates(service: SaaSService, ctx: TenantContext, campaign: dict):
    default_template = service.create_reply_template(ctx, {"name": "Default", "content": "Contact {{contact}}", "is_default": True})
    with pytest.raises(ServiceConflictError, match="default_reply_template_in_use"):
        service.archive_reply_template(ctx, default_template["id"])

    rule_template = service.create_reply_template(ctx, {"name": "Rule", "content": "Email {{email}}"})
    service.create_reply_match_rule(ctx, {"campaign_id": campaign["id"], "reply_template_id": rule_template["id"], "name": "Rule", "contains_any_json": ["price"]})
    with pytest.raises(ServiceConflictError, match="reply_template_in_use_by_rule"):
        service.archive_reply_template(ctx, rule_template["id"])


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


def test_reply_candidate_reject_cancel_bulk_and_content_guards(service: SaaSService, ctx: TenantContext, campaign: dict):
    template = service.create_reply_template(ctx, {"name": "WhatsApp", "content": "My WhatsApp is {{whatsapp}}", "is_default": True})
    service.create_reply_match_rule(ctx, {"campaign_id": campaign["id"], "reply_template_id": template["id"], "name": "Contact", "contains_any_json": ["contact"]})
    execution = _execution(service, ctx, campaign)
    _scan_artifact(
        service,
        ctx,
        execution["id"],
        [
            {"comment_id": "c1", "author_name": "Buyer 1", "text": "Can I contact you?", "fingerprint": "fp1"},
            {"comment_id": "c2", "author_name": "Buyer 2", "text": "Need contact info", "fingerprint": "fp2"},
            {"comment_id": "c3", "author_name": "Buyer 3", "text": "Please contact me", "fingerprint": "fp3"},
        ],
    )
    service.generate_reply_plan_for_execution(ctx, execution["id"])
    candidates = service.list_reply_candidates(ctx)["items"]

    with pytest.raises(ValueError, match="reject_reason_required"):
        service.reject_reply_candidate(ctx, candidates[0]["id"])
    rejected = service.reject_reply_candidate(ctx, candidates[0]["id"], "Not relevant")
    cancelled = service.cancel_reply_candidate(ctx, candidates[1]["id"])
    bulk = service.bulk_approve_reply_candidates(ctx, [candidates[2]["id"]])

    assert rejected["blocked_reason"] == "Not relevant"
    assert cancelled["status"] == "cancelled"
    assert bulk["updated"] == 1
    with pytest.raises(ServiceConflictError, match="candidate_content_locked"):
        service.update_reply_candidate_content(ctx, rejected["id"], "Edited")


def test_reply_candidate_api_requires_reason_and_supports_bulk_actions(service: SaaSService, ctx: TenantContext, campaign: dict):
    template = service.create_reply_template(ctx, {"name": "WhatsApp", "content": "My WhatsApp is {{whatsapp}}", "is_default": True})
    service.create_reply_match_rule(ctx, {"campaign_id": campaign["id"], "reply_template_id": template["id"], "name": "Contact", "contains_any_json": ["contact"]})
    execution = _execution(service, ctx, campaign)
    _scan_artifact(
        service,
        ctx,
        execution["id"],
        [
            {"comment_id": "c1", "author_name": "Buyer 1", "text": "Can I contact you?", "fingerprint": "fp1"},
            {"comment_id": "c2", "author_name": "Buyer 2", "text": "Need contact info", "fingerprint": "fp2"},
        ],
    )
    service.generate_reply_plan_for_execution(ctx, execution["id"])
    candidates = service.list_reply_candidates(ctx)["items"]
    client = TestClient(create_app(service=service))
    token = service.login("owner@example.com", "password123")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    missing_reason = client.post(f"/api/reply-candidates/{candidates[0]['id']}/reject", headers=headers, json={})
    rejected = client.post("/api/reply-candidates/bulk-reject", headers=headers, json={"candidate_ids": [candidates[0]["id"]], "reason": "Duplicate"})
    approved = client.post("/api/reply-candidates/bulk-approve", headers=headers, json={"candidate_ids": [candidates[1]["id"]]})

    assert missing_reason.status_code == 422
    assert missing_reason.json()["error"]["fields"][0]["field"] == "reason"
    assert rejected.status_code == 200
    assert rejected.json()["updated"] == 1
    assert approved.status_code == 200
    assert approved.json()["updated"] == 1


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
