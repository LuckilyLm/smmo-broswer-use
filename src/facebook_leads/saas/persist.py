from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import and_, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import TABLES, utc_now
from .storage import SaaSStorage, _prepare_payload


def persist_orchestrator_result(
    storage: SaaSStorage,
    *,
    tenant_id: str,
    campaign_id: str,
    platform_account_id: str,
    platform: str,
    result: dict[str, Any],
    execution_id: str | None = None,
    execution_keyword_id: str | None = None,
    keyword: str | None = None,
) -> dict[str, Any]:
    scan = result.get("scan_summary") or {}
    plan = result.get("batch_plan_summary") or {}
    execution_data = {
            "tenant_id": tenant_id,
            "campaign_id": campaign_id,
            "run_id": result.get("run_id"),
            "platform": platform,
            "status": result.get("status") or "unknown",
            "stage": result.get("stage"),
            "started_at": result.get("started_at"),
            "finished_at": result.get("finished_at"),
            "elapsed_ms": int(result.get("elapsed_ms") or 0),
            "scanned_contents": int(scan.get("scanned_contents") or scan.get("successful_content_count") or 0),
            "scanned_comments": int(scan.get("scanned_comments") or 0),
            "lead_candidates": int(scan.get("lead_candidates") or 0),
            "eligible_count": int(plan.get("eligible_count") or 0),
            "selected_count": int(plan.get("selected_count") or 0),
            "send_disabled": True,
            "error_type": result.get("error_type"),
            "error_message": result.get("error_message"),
    }
    if execution_id:
        execution_payload = storage.get_by_id("executions", execution_id, tenant_id=tenant_id) or {"id": execution_id, **execution_data}
    else:
        execution_payload = _prepare_payload("executions", execution_data)
        storage.insert("executions", execution_payload)
    report = _load_report(result)
    review = result.get("llm_review_summary") or {}
    for raw in _iter_report_leads(report):
        storage.upsert_lead(_lead_payload(raw, tenant_id, campaign_id, platform_account_id, platform, result, keyword=keyword))
    if review:
        storage.insert(
            "token_usage",
            {
                "tenant_id": tenant_id,
                "campaign_id": campaign_id,
                "execution_id": execution_payload["id"],
                "execution_keyword_id": execution_keyword_id,
                "provider": platform,
                "model": review.get("model"),
                "prompt_tokens": review.get("prompt_tokens"),
                "completion_tokens": review.get("completion_tokens"),
                "total_tokens": review.get("total_tokens"),
                "request_count": review.get("call_count"),
                "estimated_cost": None,
            },
        )
    return storage.get_by_id("executions", execution_payload["id"]) or execution_payload


def _lead_payload(raw: dict[str, Any], tenant_id: str, campaign_id: str, platform_account_id: str, platform: str, result: dict[str, Any], *, keyword: str | None = None) -> dict[str, Any]:
    review = raw.get("llm_review") or {}
    discovered_at = result.get("finished_at") or utc_now()
    return {
        "tenant_id": tenant_id,
        "campaign_id": campaign_id,
        "platform_account_id": platform_account_id,
        "platform": platform,
        "external_lead_id": raw.get("comment_id") or raw.get("comment_fingerprint"),
        "comment_id": raw.get("comment_id"),
        "comment_fingerprint": raw.get("comment_fingerprint"),
        "author_name": raw.get("author_name"),
        "author_url": raw.get("author_url"),
        "comment_text": raw.get("comment_text"),
        "source_content_url": raw.get("source_content_url"),
        "direct_comment_url": raw.get("direct_comment_url"),
        "rule_intent_level": raw.get("rule_intent_level") or raw.get("intent_level"),
        "llm_confidence": review.get("confidence"),
        "llm_intent_level": review.get("intent_level") or raw.get("final_intent_level"),
        "llm_intent_types": review.get("intent_types") or raw.get("final_intent_types") or [],
        "llm_reason": review.get("reason_zh") or raw.get("final_reason_zh"),
        "suggested_reply": review.get("suggested_reply") or raw.get("final_suggested_reply"),
        "ownership_status": raw.get("ownership_status"),
        "reply_allowed": bool(raw.get("reply_allowed")),
        "status": "blocked" if raw.get("reply_allowed") is False else "new",
        "matched_search_keywords": [keyword] if keyword else [],
        "first_discovered_at": discovered_at,
        "last_discovered_at": discovered_at,
        "discovered_at": discovered_at,
    }


def _load_report(result: dict[str, Any]) -> dict[str, Any]:
    paths = result.get("paths") or {}
    for key in ("lead_report_enriched_json", "lead_report_json"):
        path = paths.get(key)
        if path and Path(path).exists():
            return json.loads(Path(path).read_text(encoding="utf-8"))
    return result.get("lead_report") or {}


def _iter_report_leads(report: dict[str, Any]):
    for content in report.get("contents") or []:
        for lead in content.get("leads") or []:
            yield lead
