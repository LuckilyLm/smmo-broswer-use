from __future__ import annotations

import json

import pytest

from src.facebook_leads.saas.persist import persist_orchestrator_result
from src.facebook_leads.saas.service import SaaSService
from src.facebook_leads.saas.storage import SaaSStorage


def _workspace(tmp_path):
    storage = SaaSStorage(tmp_path / "transaction.sqlite")
    service = SaaSService(storage)
    tenant = service.create_tenant("Transaction", "transaction")
    user = service.create_user("transaction@example.com", "pass123456", "Admin")
    service.add_user_to_tenant(tenant["id"], user["id"], role="admin")
    context = service.context_from_token(service.login("transaction@example.com", "pass123456")["access_token"])
    account = service.create_platform_account(context, {"platform": "facebook", "display_name": "Page"})
    campaign = service.create_campaign(context, {"name": "Campaign", "platform_account_id": account["id"]})
    execution = storage.insert(
        "executions",
        {"tenant_id": tenant["id"], "campaign_id": campaign["id"], "platform": "facebook", "status": "running", "stage": "worker", "started_at": "2026-07-29T01:00:00+00:00", "send_disabled": True},
    )
    return storage, tenant, account, campaign, execution


def _result(tmp_path, fingerprint: str):
    report = tmp_path / f"{fingerprint}.json"
    report.write_text(
        json.dumps(
            {
                "contents": [
                    {
                        "leads": [
                            {
                                "comment_id": fingerprint,
                                "comment_fingerprint": fingerprint,
                                "comment_text": "Price please",
                                "reply_allowed": False,
                            }
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return {
        "run_id": f"run-{fingerprint}",
        "status": "completed",
        "stage": "completed",
        "started_at": "2026-07-29T02:00:00+00:00",
        "finished_at": "2026-07-29T02:00:01+00:00",
        "scan_summary": {"scanned_contents": 1, "scanned_comments": 1, "lead_candidates": 1},
        "batch_plan_summary": {"eligible_count": 0, "selected_count": 0},
        "llm_review_summary": {"model": "gpt-5.5", "prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12, "call_count": 1},
        "paths": {"lead_report_enriched_json": str(report)},
        "send_disabled": True,
    }


def _persist(storage, tenant, account, campaign, execution, result, keyword_id):
    return persist_orchestrator_result(
        storage,
        tenant_id=tenant["id"],
        campaign_id=campaign["id"],
        platform_account_id=account["id"],
        platform="facebook",
        result=result,
        execution_id=execution["id"],
        execution_keyword_id=keyword_id,
        keyword="massage chair",
    )


def test_persist_preserves_unknown_reply_allowed(tmp_path):
    storage, tenant, account, campaign, execution = _workspace(tmp_path)
    result = _result(tmp_path, "unknown-eligibility")
    report_path = result["paths"]["lead_report_enriched_json"]
    with open(report_path, encoding="utf-8") as handle:
        report = json.load(handle)
    del report["contents"][0]["leads"][0]["reply_allowed"]
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle)

    _persist(storage, tenant, account, campaign, execution, result, "keyword-unknown")

    lead = storage.find_one("leads", {"comment_fingerprint": "unknown-eligibility"})
    assert lead is not None
    assert lead["reply_allowed"] is None
    assert lead["status"] == "new"


def test_explicit_reply_block_remains_distinct_from_unknown(tmp_path):
    storage, tenant, account, campaign, execution = _workspace(tmp_path)

    _persist(storage, tenant, account, campaign, execution, _result(tmp_path, "explicit-block"), "keyword-blocked")

    lead = storage.find_one("leads", {"comment_fingerprint": "explicit-block"})
    assert lead is not None
    assert lead["reply_allowed"] is False
    assert lead["status"] == "blocked"


def test_existing_parent_lifecycle_is_not_overwritten_by_keyword_result(tmp_path):
    storage, tenant, account, campaign, execution = _workspace(tmp_path)

    persisted = _persist(storage, tenant, account, campaign, execution, _result(tmp_path, "lifecycle"), "keyword-lifecycle")

    assert persisted["status"] == "running"
    assert persisted["stage"] == "worker"
    assert persisted["started_at"] == execution["started_at"]
    assert persisted["finished_at"] is None
    assert persisted["run_id"] == "run-lifecycle"
    assert persisted["scanned_comments"] == 1
    assert storage.count("leads", tenant_id=tenant["id"]) == 1
    assert storage.count("token_usage", tenant_id=tenant["id"]) == 1


def test_persist_result_rolls_back_execution_leads_and_tokens_together(tmp_path, monkeypatch):
    storage, tenant, account, campaign, execution = _workspace(tmp_path)
    original_insert = storage.insert

    def failing_insert(table, data, *, session=None):
        if table == "token_usage":
            raise RuntimeError("token insert failed")
        return original_insert(table, data, session=session)

    monkeypatch.setattr(storage, "insert", failing_insert)

    with pytest.raises(RuntimeError, match="token insert failed"):
        _persist(storage, tenant, account, campaign, execution, _result(tmp_path, "rollback"), "keyword-1")

    rolled_back = storage.get_by_id("executions", execution["id"])
    assert rolled_back["status"] == "running"
    assert rolled_back["stage"] == "worker"
    assert rolled_back["started_at"] == execution["started_at"]
    assert storage.count("leads", tenant_id=tenant["id"]) == 0
    assert storage.count("token_usage", tenant_id=tenant["id"]) == 0


def test_each_keyword_persist_has_an_independent_transaction(tmp_path, monkeypatch):
    storage, tenant, account, campaign, execution = _workspace(tmp_path)
    _persist(storage, tenant, account, campaign, execution, _result(tmp_path, "keyword-a"), "keyword-a")
    original_insert = storage.insert

    def fail_second_token(table, data, *, session=None):
        if table == "token_usage" and data.get("execution_keyword_id") == "keyword-b":
            raise RuntimeError("second keyword failed")
        return original_insert(table, data, session=session)

    monkeypatch.setattr(storage, "insert", fail_second_token)

    with pytest.raises(RuntimeError, match="second keyword failed"):
        _persist(storage, tenant, account, campaign, execution, _result(tmp_path, "keyword-b"), "keyword-b")

    assert storage.count("leads", tenant_id=tenant["id"]) == 1
    assert storage.count("token_usage", tenant_id=tenant["id"]) == 1
    assert storage.find_one("leads", {"comment_fingerprint": "keyword-a"}) is not None
    assert storage.find_one("leads", {"comment_fingerprint": "keyword-b"}) is None
