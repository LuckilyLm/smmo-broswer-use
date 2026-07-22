from __future__ import annotations

import asyncio
import html
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from .diagnostics import write_json
from .intent_models import IntentMatch, LeadCandidate
from .llm_review import (
    LLM_REVIEW_PROMPT_VERSION,
    apply_review_to_leads,
    review_leads_with_llm_detailed,
)
from .reply import (
    DEFAULT_REPLY_HISTORY_PATH,
    ReplyRequest,
    _ordered_report_leads,
    build_reply_idempotency_key,
    find_blocking_reply_history,
    find_successful_duplicate,
    reply_to_comment,
)
from .target_policy import TargetPolicyConfig, build_target_policy_config, evaluate_source_policy


DEFAULT_BATCH_MAX = 5
DEFAULT_DAILY_LIMIT = 10
DEFAULT_INTERVAL_SECONDS = 30.0
DEFAULT_ACCEPTANCE_MAX = 2
STOP_STATUSES = {"unverified"}
STOP_ERROR_TYPES = {"unexpected_existing_draft"}


@dataclass(frozen=True)
class BatchPlanConfig:
    max_leads: int = DEFAULT_BATCH_MAX
    min_confidence: float = 0.90
    daily_limit: int = DEFAULT_DAILY_LIMIT
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    history_path: str | Path = DEFAULT_REPLY_HISTORY_PATH
    target_policy: TargetPolicyConfig = field(default_factory=build_target_policy_config)


@dataclass(frozen=True)
class BatchExecuteConfig:
    execute: bool = False
    confirm_send: bool = False
    confirmed: bool = False
    dry_run: bool = False
    preflight_only: bool = False
    max_leads: int = DEFAULT_BATCH_MAX
    daily_limit: int = DEFAULT_DAILY_LIMIT
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS
    history_path: str | Path = DEFAULT_REPLY_HISTORY_PATH
    artifacts_dir: str | Path = "artifacts/facebook_leads/batch_replies"
    acceptance_test: bool = False
    acceptance_max: int = DEFAULT_ACCEPTANCE_MAX


@dataclass
class BatchPlan:
    plan_id: str
    generated_at: str
    lead_report_path: str
    min_confidence: float
    max_leads: int
    daily_limit: int
    daily_verified_before: int
    daily_remaining: int
    summary: dict[str, Any]
    items: list[dict[str, Any]] = field(default_factory=list)
    phase5_1_review: dict[str, Any] = field(default_factory=dict)
    paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_batch_max(value: int | None = None, env: dict[str, str] | None = None) -> int:
    return _resolve_positive_int(value, "FACEBOOK_LEADS_REPLY_BATCH_MAX", DEFAULT_BATCH_MAX, env)


def resolve_daily_limit(value: int | None = None, env: dict[str, str] | None = None) -> int:
    return _resolve_positive_int(value, "FACEBOOK_LEADS_REPLY_DAILY_LIMIT", DEFAULT_DAILY_LIMIT, env)


def resolve_interval_seconds(value: float | None = None, env: dict[str, str] | None = None) -> float:
    if value is not None:
        if value < 0:
            raise ValueError("--interval-seconds must be >= 0")
        return float(value)
    raw = (env or os.environ).get("FACEBOOK_LEADS_REPLY_INTERVAL_SECONDS")
    if not raw:
        return DEFAULT_INTERVAL_SECONDS
    resolved = float(raw)
    if resolved < 0:
        raise ValueError("FACEBOOK_LEADS_REPLY_INTERVAL_SECONDS must be >= 0")
    return resolved


def resolve_acceptance_max(value: int | None = None, env: dict[str, str] | None = None) -> int:
    resolved = _resolve_positive_int(value, "FACEBOOK_LEADS_REPLY_ACCEPTANCE_MAX", DEFAULT_ACCEPTANCE_MAX, env)
    if resolved > DEFAULT_ACCEPTANCE_MAX:
        raise ValueError("FACEBOOK_LEADS_REPLY_ACCEPTANCE_MAX/--acceptance-max must be between 1 and 2")
    return resolved


def build_batch_plan(
    lead_report_path: str | Path,
    *,
    config: BatchPlanConfig,
    now: datetime | None = None,
) -> BatchPlan:
    generated = now or datetime.now(timezone.utc)
    data = json.loads(Path(lead_report_path).read_text(encoding="utf-8"))
    leads = _ordered_report_leads(data)
    daily_before = count_today_verified_replies(config.history_path, now=generated)
    daily_remaining = max(int(config.daily_limit) - daily_before, 0)
    items: list[dict[str, Any]] = []
    selected_count = 0
    already_replied_count = 0
    unverified_blocked_count = 0
    for lead_index, lead in enumerate(leads, start=1):
        item = build_plan_item(
            lead,
            lead_index=lead_index,
            min_confidence=config.min_confidence,
            history_path=config.history_path,
            target_policy=config.target_policy,
        )
        if "duplicate_history" in item["blocking_reasons"]:
            already_replied_count += 1
        if "unverified_previous_attempt" in item["blocking_reasons"]:
            unverified_blocked_count += 1
        if item["eligible"] and selected_count < min(config.max_leads, daily_remaining):
            item["selected"] = True
            selected_count += 1
        items.append(item)
    eligible_count = sum(1 for item in items if item["eligible"])
    blocked_count = sum(1 for item in items if not item["eligible"])
    plan = BatchPlan(
        plan_id=f"plan_{generated.strftime('%Y%m%d_%H%M%S')}",
        generated_at=generated.isoformat(),
        lead_report_path=str(lead_report_path),
        min_confidence=config.min_confidence,
        max_leads=config.max_leads,
        daily_limit=config.daily_limit,
        daily_verified_before=daily_before,
        daily_remaining=daily_remaining,
        summary={
            "total_leads": len(leads),
            "eligible_count": eligible_count,
            "selected_count": selected_count,
            "blocked_count": blocked_count,
            "already_replied_count": already_replied_count,
            "unverified_blocked_count": unverified_blocked_count,
            "target_policy": config.target_policy.policy,
            "owned_source_count": config.target_policy.owned_source_count,
            "allowlisted_source_count": config.target_policy.allowlisted_source_count,
            "reply_allowed_count": sum(1 for item in items if item.get("reply_allowed")),
            "discovery_only_blocked_count": sum(1 for item in items if "source_not_allowed" in (item.get("blocking_reasons") or [])),
        },
        items=items,
        phase5_1_review=dict(data.get("phase5_1_review") or {}),
    )
    return plan


def build_plan_item(
    lead: dict[str, Any],
    *,
    lead_index: int,
    min_confidence: float,
    history_path: str | Path,
    target_policy: TargetPolicyConfig | None = None,
) -> dict[str, Any]:
    target_policy = target_policy or build_target_policy_config()
    review = lead.get("llm_review") or {}
    suggested_reply = str(review.get("suggested_reply") or "").strip()
    confidence = _safe_float(review.get("confidence"))
    request = ReplyRequest(
        source_content_url=lead.get("source_content_url") or "",
        direct_comment_url=lead.get("direct_comment_url"),
        comment_id=lead.get("comment_id"),
        author_name=lead.get("author_name"),
        comment_text=lead.get("comment_text"),
        fingerprint=lead.get("comment_fingerprint"),
        reply_text=suggested_reply,
        confirm_send=True,
        yes=True,
        lead_index=lead_index,
        reply_source="llm_suggested",
    )
    idempotency_key = build_reply_idempotency_key(request)
    blocking = []
    ownership = evaluate_source_policy(lead, target_policy)
    if review.get("status") != "success":
        blocking.append("llm_review_not_success")
    if review.get("is_lead") is not True:
        blocking.append("llm_not_lead")
    if review.get("should_reply") is not True:
        blocking.append("llm_should_reply_false")
    if not suggested_reply:
        blocking.append("suggested_reply_empty")
    if confidence < min_confidence:
        blocking.append("confidence_below_threshold")
    if not (lead.get("comment_id") or lead.get("direct_comment_url")):
        blocking.append("comment_locator_missing")
    history = find_blocking_reply_history(
        history_path,
        comment_id=lead.get("comment_id"),
        fingerprint=lead.get("comment_fingerprint"),
        idempotency_key=idempotency_key,
        reply_text=suggested_reply,
    )
    if history:
        if history.get("block_status") == "blocked_unverified_previous_attempt":
            blocking.append("unverified_previous_attempt")
        else:
            blocking.append("duplicate_history")
    if lead.get("review_attempt_source") == "already_verified_reply" and "duplicate_history" not in blocking:
        blocking.append("duplicate_history")
    if not ownership["reply_allowed"]:
        blocking.append("source_not_allowed")
    eligible = not blocking
    return {
        "plan_index": lead_index,
        "lead_index": lead_index,
        "author_name": lead.get("author_name"),
        "comment_id": lead.get("comment_id"),
        "comment_fingerprint": lead.get("comment_fingerprint"),
        "comment_text": lead.get("comment_text"),
        "source_content_url": lead.get("source_content_url"),
        "direct_comment_url": lead.get("direct_comment_url"),
        "rule_intent_level": lead.get("rule_intent_level") or lead.get("intent_level"),
        "llm_review_status": review.get("status"),
        "llm_review_source": lead.get("llm_review_source") or _llm_review_source_for_lead(lead),
        "llm_reason_zh": review.get("reason_zh") or lead.get("final_reason_zh"),
        "llm_is_lead": review.get("is_lead"),
        "llm_confidence": confidence,
        "should_reply": review.get("should_reply"),
        "suggested_reply": suggested_reply,
        "reply_source": "llm_suggested",
        "idempotency_key": idempotency_key,
        **ownership,
        "eligible": eligible,
        "blocking_reasons": blocking,
        "selected": False,
    }


def write_batch_plan_files(plan: BatchPlan, output_dir: str | Path) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "batch_reply_plan.json"
    html_path = output / "batch_reply_plan.html"
    paths = {"batch_reply_plan_json": str(json_path), "batch_reply_plan_html": str(html_path)}
    plan.paths.update(paths)
    write_json(json_path, plan.to_dict())
    html_path.write_text(render_batch_plan_html(plan), encoding="utf-8")
    write_json(json_path, plan.to_dict())
    return paths


async def enrich_lead_report_missing_reviews(
    lead_report_path: str | Path,
    *,
    output_dir: str | Path,
    history_path: str | Path = DEFAULT_REPLY_HISTORY_PATH,
    batch_size: int = 10,
    llm_client: Any | None = None,
    model_name: str | None = None,
    concurrency: int | None = None,
    timeout_seconds: float | None = None,
    max_batch_chars: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    source_path = Path(lead_report_path)
    report = json.loads(source_path.read_text(encoding="utf-8"))
    decisions = collect_missing_review_decisions(report, history_path=history_path)
    requested = [item for item in decisions if item["action"] == "review"]
    review_payload: dict[str, Any] | None = None
    reviewed_by_fingerprint: dict[str, LeadCandidate] = {}
    if requested and not dry_run:
        review_payload = await review_leads_with_llm_detailed(
            [item["lead_model"] for item in requested],
            batch_size=batch_size,
            llm_client=llm_client,
            model_name=model_name,
            concurrency=concurrency,
            timeout_seconds=timeout_seconds,
            max_batch_chars=max_batch_chars,
        )
        reviewed_models = apply_review_to_leads(
            [item["lead_model"] for item in requested],
            review_payload["reviewed"],
        )
        reviewed_by_fingerprint = {lead.comment_fingerprint: lead for lead in reviewed_models}

    for item in decisions:
        raw = item["raw"]
        if item["action"] == "existing":
            raw["llm_review_source"] = "existing"
            raw["review_attempt_source"] = "existing"
        elif item["action"] == "skip_verified":
            raw["llm_review_source"] = "not_reviewed"
            raw["review_attempt_source"] = "already_verified_reply"
        elif item["action"] == "review" and dry_run:
            raw["llm_review_source"] = "not_reviewed"
            raw["review_attempt_source"] = item["attempt_source"]
        elif item["action"] == "review":
            reviewed = reviewed_by_fingerprint.get(item["lead_model"].comment_fingerprint)
            if reviewed is not None:
                raw.update(reviewed.to_dict())
                raw["llm_review_source"] = "phase5_1_reviewed" if reviewed.llm_review_status == "success" else "phase5_1_fallback"
                raw["review_attempt_source"] = item["attempt_source"]

    summary = build_phase5_1_review_summary(
        decisions,
        review_payload=review_payload,
        elapsed_ms=int((time.perf_counter() - started) * 1000),
        dry_run=dry_run,
        model_name=model_name,
    )
    report["phase5_1_review"] = summary
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "lead_report_enriched.json"
    html_path = output / "lead_report_enriched.html"
    write_json(json_path, report)
    html_path.write_text(render_enriched_lead_report_html(report), encoding="utf-8")
    return {
        "lead_report": report,
        "summary": summary,
        "paths": {
            "lead_report_enriched_json": str(json_path),
            "lead_report_enriched_html": str(html_path),
        },
    }


def collect_missing_review_decisions(report: dict[str, Any], *, history_path: str | Path) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for content in report.get("contents") or []:
        for raw in content.get("leads") or []:
            if not isinstance(raw, dict):
                continue
            status = _lead_llm_status(raw)
            duplicate = find_successful_duplicate(
                history_path,
                comment_id=raw.get("comment_id"),
                fingerprint=raw.get("comment_fingerprint"),
                reply_text=None,
            )
            if status == "success":
                decisions.append(
                    {
                        "action": "existing",
                        "raw": raw,
                        "reason": "existing_success",
                        "has_verified_history": bool(duplicate),
                    }
                )
                continue
            if duplicate:
                decisions.append(
                    {
                        "action": "skip_verified",
                        "raw": raw,
                        "reason": "already_verified_reply",
                        "has_verified_history": True,
                    }
                )
                continue
            lead_model = lead_candidate_from_dict(raw, content)
            decisions.append(
                {
                    "action": "review",
                    "raw": raw,
                    "lead_model": lead_model,
                    "reason": status or "missing",
                    "attempt_source": _review_attempt_source(status),
                    "has_verified_history": False,
                }
            )
    return decisions


def build_phase5_1_review_summary(
    decisions: list[dict[str, Any]],
    *,
    review_payload: dict[str, Any] | None,
    elapsed_ms: int,
    dry_run: bool,
    model_name: str | None,
) -> dict[str, Any]:
    requested = [item for item in decisions if item["action"] == "review"]
    existing_success_count = sum(1 for item in decisions if item["action"] == "existing")
    verified_skipped_count = sum(1 for item in decisions if item["action"] == "skip_verified")
    verified_history_count = sum(1 for item in decisions if item.get("has_verified_history"))
    llm_summary = (review_payload or {}).get("summary") or {}
    return {
        "enabled": not dry_run,
        "dry_run": dry_run,
        "existing_success_count": existing_success_count,
        "verified_skipped_count": verified_skipped_count,
        "verified_history_count": verified_history_count,
        "verified_skipped_from_review_count": verified_skipped_count,
        "missing_count": len(requested),
        "missing_llm_review_count": len(requested),
        "requested_count": 0 if dry_run else len(requested),
        "success_count": int(llm_summary.get("success_count") or 0),
        "fallback_count": int(llm_summary.get("fallback_count") or 0),
        "model": llm_summary.get("model") or model_name,
        "prompt_version": llm_summary.get("prompt_version") or LLM_REVIEW_PROMPT_VERSION,
        "call_count": int(llm_summary.get("call_count") or 0),
        "elapsed_ms": elapsed_ms,
        "prompt_tokens": llm_summary.get("prompt_tokens"),
        "completion_tokens": llm_summary.get("completion_tokens"),
        "total_tokens": llm_summary.get("total_tokens"),
        "review_sources": {
            "existing": existing_success_count,
            "already_verified_reply": verified_skipped_count,
            "phase5_1_requested": len(requested),
            "verified_history": verified_history_count,
        },
    }


def lead_candidate_from_dict(raw: dict[str, Any], content: dict[str, Any]) -> LeadCandidate:
    matches = [
        IntentMatch(
            keyword=str(item.get("keyword") or ""),
            normalized_keyword=str(item.get("normalized_keyword") or item.get("keyword") or ""),
            category=str(item.get("category") or "other"),
            language=str(item.get("language") or "unknown"),
            weight=int(item.get("weight") or 0),
            matched_text=str(item.get("matched_text") or item.get("keyword") or ""),
        )
        for item in raw.get("matched_keywords") or []
        if isinstance(item, dict)
    ]
    return LeadCandidate(
        comment_fingerprint=str(raw.get("comment_fingerprint") or raw.get("fingerprint") or ""),
        comment_id=raw.get("comment_id"),
        author_name=raw.get("author_name"),
        author_url=raw.get("author_url"),
        author_extract_strategy=raw.get("author_extract_strategy"),
        comment_text=raw.get("comment_text"),
        timestamp_text=raw.get("timestamp_text"),
        comment_url=raw.get("comment_url"),
        direct_comment_url=raw.get("direct_comment_url"),
        comment_id_source=raw.get("comment_id_source"),
        source_content_url=str(raw.get("source_content_url") or content.get("source_content_url") or ""),
        source_discovered_url=raw.get("source_discovered_url") or content.get("discovered_url"),
        source_final_url=raw.get("source_final_url") or content.get("final_url"),
        source_content_type=raw.get("source_content_type") or content.get("content_type"),
        source_text_preview=raw.get("source_text_preview") or content.get("text_preview"),
        source_author_name=raw.get("source_author_name") or content.get("author_name"),
        intent_score=int(raw.get("intent_score") or 0),
        intent_level=raw.get("intent_level") or "low",
        matched_keywords=matches,
        matched_categories=list(raw.get("matched_categories") or []),
        raw_matched_keywords=list(raw.get("raw_matched_keywords") or []),
        effective_matched_keywords=list(raw.get("effective_matched_keywords") or []),
        deduplicated_keywords=list(raw.get("deduplicated_keywords") or []),
        score_breakdown=dict(raw.get("score_breakdown") or {}),
        reasons=list(raw.get("reasons") or []),
        is_false_positive=bool(raw.get("is_false_positive")),
        false_positive_reason=raw.get("false_positive_reason"),
        comment_locator_data=dict(raw.get("comment_locator_data") or {}),
        rule_intent_score=raw.get("rule_intent_score"),
        rule_intent_level=raw.get("rule_intent_level"),
        rule_matched_keywords=list(raw.get("rule_matched_keywords") or []),
        rule_matched_categories=list(raw.get("rule_matched_categories") or []),
        llm_review=raw.get("llm_review"),
        llm_review_status=raw.get("llm_review_status") or "disabled",
        final_is_lead=raw.get("final_is_lead"),
        final_intent_level=raw.get("final_intent_level"),
        final_intent_types=list(raw.get("final_intent_types") or []),
        final_reason_zh=raw.get("final_reason_zh"),
        final_suggested_reply=raw.get("final_suggested_reply"),
        decision_source=raw.get("decision_source") or "rule_only",
    )


async def execute_batch_plan(
    plan: dict[str, Any] | BatchPlan,
    *,
    config: BatchExecuteConfig,
    page: Any = None,
    reply_runner: Callable[[Any, ReplyRequest], Awaitable[dict[str, Any]]] | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    now: datetime | None = None,
    persist: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    plan_dict = plan.to_dict() if isinstance(plan, BatchPlan) else plan
    started_at = now or datetime.now(timezone.utc)
    batch_id = f"batch_{started_at.strftime('%Y%m%d_%H%M%S')}"
    selected = [item for item in plan_dict.get("items", []) if item.get("selected")]
    acceptance_max = resolve_acceptance_max(config.acceptance_max) if config.acceptance_test else None
    execution_limit = acceptance_max if acceptance_max is not None else config.max_leads
    acceptance_subset = selected[: min(execution_limit, len(selected))]
    max_attempts = min(execution_limit, len(selected))
    daily_before = count_today_verified_replies(config.history_path, now=started_at)
    daily_remaining = max(config.daily_limit - daily_before, 0)
    execution_mode = _execution_mode(config)
    batch_unverified_lock = _has_batch_unverified_lock(plan_dict)
    result: dict[str, Any] = {
        "batch_id": batch_id,
        "plan_id": plan_dict.get("plan_id"),
        "status": "running",
        "execution_mode": execution_mode,
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "elapsed_ms": None,
        "planned_count": len(selected),
        "plan_selected_count": len(selected),
        "acceptance_test": bool(config.acceptance_test),
        "acceptance_max": acceptance_max,
        "acceptance_subset_count": len(acceptance_subset) if config.acceptance_test else None,
        "acceptance_subset_plan_indexes": [item.get("plan_index") for item in acceptance_subset] if config.acceptance_test else [],
        "attempted_count": 0,
        "verified_count": 0,
        "duplicate_count": 0,
        "blocked_count": 0,
        "unverified_count": 0,
        "failed_count": 0,
        "send_failed_count": 0,
        "total_send_action_count": 0,
        "preflight_passed_count": 0,
        "preflight_failed_count": 0,
        "ready_for_real_batch_acceptance": False,
        "daily_limit": config.daily_limit,
        "daily_verified_before": daily_before,
        "daily_verified_after": daily_before,
        "daily_remaining": daily_remaining,
        "interval_seconds": config.interval_seconds,
        "batch_unverified_lock": batch_unverified_lock,
        "batch_safety": _initial_batch_safety(),
        "results": [],
    }
    _refresh_batch_safety(result)
    if persist:
        persist(result)
    if config.execute and (not config.confirm_send or not config.confirmed):
        result["status"] = "cancelled"
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        result["elapsed_ms"] = _elapsed_ms(started_at)
        result["cancelled_reason"] = "Batch execution requires --execute, --confirm-send, and SEND BATCH confirmation"
        _refresh_batch_safety(result)
        if persist:
            persist(result)
        return result
    if daily_remaining <= 0:
        result["status"] = "daily_limit_reached"
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        result["elapsed_ms"] = _elapsed_ms(started_at)
        _refresh_batch_safety(result)
        if persist:
            persist(result)
        return result
    result["status"] = "preflight_only" if config.preflight_only else ("dry_run" if config.dry_run else "completed")
    if persist:
        persist(result)
    attempts_allowed = min(max_attempts, daily_remaining)
    runner = reply_runner or _default_reply_runner
    sleeper = sleep or asyncio.sleep
    for item in selected[:attempts_allowed]:
        request = request_from_plan_item(
            item,
            confirm_send=bool(config.execute and config.confirm_send and config.confirmed and not config.dry_run and not config.preflight_only),
            plan_id=str(plan_dict.get("plan_id") or ""),
            batch_id=batch_id,
            acceptance_test=config.acceptance_test,
        )
        payload = _source_not_allowed_payload(request) if item.get("reply_allowed") is False else None
        if payload is None:
            payload = _preflight_history_duplicate_payload(request, config.history_path) if config.preflight_only else None
        if payload is None:
            try:
                payload = await runner(page, request)
            except Exception as exc:
                payload = _exception_payload(request, exc)
        entry = summarize_single_result(item, payload, execution_mode=execution_mode)
        result["results"].append(entry)
        result["attempted_count"] += 1
        _increment_result_counts(result, entry)
        result["total_send_action_count"] = sum(int(item.get("send_action_count") or 0) for item in result["results"])
        _refresh_preflight_counts(result)
        result["daily_verified_after"] = daily_before + result["verified_count"]
        _refresh_batch_safety(result)
        _refresh_acceptance_readiness(result)
        if persist:
            persist(result)
        stop_status = _batch_stop_status(entry)
        if config.acceptance_test and result["total_send_action_count"] > (acceptance_max or DEFAULT_ACCEPTANCE_MAX):
            stop_status = "failed"
        if stop_status:
            result["status"] = stop_status
            break
        if result["attempted_count"] < attempts_allowed and config.interval_seconds > 0 and not (config.dry_run or config.preflight_only):
            await sleeper(config.interval_seconds)
    if result["status"] == "completed" and result["attempted_count"] < len(selected) and result["attempted_count"] >= daily_remaining:
        result["status"] = "daily_limit_reached"
    if result["status"] == "completed" and result["blocked_count"] + result["duplicate_count"] + result["failed_count"] > 0:
        result["status"] = "partial"
    result["daily_verified_after"] = daily_before + result["verified_count"]
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    result["elapsed_ms"] = _elapsed_ms(started_at)
    result["total_send_action_count"] = sum(int(item.get("send_action_count") or 0) for item in result["results"])
    _refresh_preflight_counts(result)
    _refresh_batch_safety(result)
    _refresh_acceptance_readiness(result)
    if persist:
        persist(result)
    return result


def request_from_plan_item(
    item: dict[str, Any],
    *,
    confirm_send: bool,
    plan_id: str,
    batch_id: str,
    acceptance_test: bool = False,
) -> ReplyRequest:
    return ReplyRequest(
        source_content_url=item.get("source_content_url") or "",
        direct_comment_url=item.get("direct_comment_url"),
        comment_id=item.get("comment_id"),
        author_name=item.get("author_name"),
        comment_text=item.get("comment_text"),
        fingerprint=item.get("comment_fingerprint"),
        reply_text=item.get("suggested_reply") or "",
        confirm_send=confirm_send,
        yes=confirm_send,
        lead_index=item.get("lead_index"),
        reply_source=item.get("reply_source") or "llm_suggested",
        plan_id=plan_id,
        batch_id=batch_id,
        plan_index=item.get("plan_index"),
        batch_mode=True,
        acceptance_test=acceptance_test,
        target_policy=item.get("target_policy"),
        ownership_status=item.get("ownership_status"),
        reply_allowed=item.get("reply_allowed"),
    )


async def _default_reply_runner(page: Any, request: ReplyRequest) -> dict[str, Any]:
    return await reply_to_comment(page, request)


def _preflight_history_duplicate_payload(request: ReplyRequest, history_path: str | Path) -> dict[str, Any] | None:
    duplicate = find_blocking_reply_history(
        history_path,
        comment_id=request.comment_id,
        fingerprint=request.fingerprint,
        idempotency_key=build_reply_idempotency_key(request),
        reply_text=request.reply_text,
    )
    if not duplicate:
        return None
    blocked_unverified = duplicate.get("block_status") == "blocked_unverified_previous_attempt"
    status = "blocked_unverified_previous_attempt" if blocked_unverified else "duplicate"
    return {
        "request": request.to_dict(),
        "result": {
            "status": status,
            "stage": "duplicate_check",
            "dry_run": True,
            "send_action_performed": False,
            "send_action_count": 0,
            "sent": False,
            "verified": False,
            "already_replied": True,
            "blocking_reasons": ["unverified_previous_attempt"] if blocked_unverified else ["duplicate_history"],
            "error_type": "unverified_previous_attempt" if blocked_unverified else "duplicate_reply",
            "error": (
                "Previous send action was performed but verification failed. Check Facebook manually before retrying."
                if blocked_unverified
                else "A verified reply already exists for this comment and reply text"
            ),
        },
        "diagnostics": {"duplicate": duplicate, "send_action_count": 0},
        "paths": {},
    }


def summarize_single_result(item: dict[str, Any], payload: dict[str, Any], *, execution_mode: str = "execute") -> dict[str, Any]:
    single = payload.get("result") or {}
    diagnostics = payload.get("diagnostics") or single.get("diagnostics") or {}
    preflight = single.get("preflight") or diagnostics.get("preflight") or {}
    composer = diagnostics.get("reply_composer") or diagnostics.get("composer") or {}
    preflight_diag = _preflight_diagnostics(item, single, diagnostics, preflight, execution_mode)
    status = _batch_item_status(single, preflight_diag, execution_mode)
    return {
        "plan_index": item.get("plan_index"),
        "lead_index": item.get("lead_index"),
        "author_name": item.get("author_name"),
        "comment_id": item.get("comment_id"),
        "comment_text": item.get("comment_text"),
        "source_content_url": item.get("source_content_url"),
        "direct_comment_url": item.get("direct_comment_url"),
        "reply_text": item.get("suggested_reply"),
        "reply_source": item.get("reply_source") or "llm_suggested",
        "idempotency_key": item.get("idempotency_key"),
        "llm_confidence": item.get("llm_confidence"),
        "llm_reason_zh": item.get("llm_reason_zh"),
        "target_policy": item.get("target_policy"),
        "ownership_status": item.get("ownership_status"),
        "reply_allowed": item.get("reply_allowed"),
        "ownership_reason": item.get("ownership_reason"),
        "execution_mode": execution_mode,
        "status": status,
        "single_status": single.get("status"),
        "stage": single.get("stage"),
        "preflight": preflight,
        **preflight_diag,
        "locate_strategy": single.get("locate_strategy") or preflight.get("locate_strategy") or diagnostics.get("locate_strategy"),
        "matched_count": single.get("matched_count") if single.get("matched_count") is not None else preflight.get("matched_count"),
        "reply_composer_found": _coalesce(single.get("input_found"), composer.get("found"), diagnostics.get("reply_composer_found")),
        "reply_composer_strategy": composer.get("strategy") or diagnostics.get("reply_composer_strategy") or ("not_checked_in_preflight" if execution_mode == "preflight_only" else None),
        "composer_send_action_matched_count": _coalesce(
            composer.get("send_action_matched_count"),
            diagnostics.get("composer_send_action_matched_count"),
            diagnostics.get("send_action_matched_count"),
            "not_checked" if execution_mode == "preflight_only" else None,
        ),
        "obstruction_detected": bool(diagnostics.get("obstruction_detected")),
        "obstruction_types": list(diagnostics.get("obstruction_types") or []),
        "obstruction_dismiss_attempted": bool(diagnostics.get("obstruction_dismiss_attempted")),
        "obstruction_dismissed_count": int(diagnostics.get("obstruction_dismissed_count") or 0),
        "reply_click_attempts": int(diagnostics.get("reply_click_attempts") or 0),
        "reply_click_obstructed": bool(diagnostics.get("reply_click_obstructed")),
        "reply_click_recovered": bool(diagnostics.get("reply_click_recovered")),
        "send_action_performed": bool(single.get("send_action_performed")),
        "send_action_count": int(diagnostics.get("send_action_count") or 0),
        "verified": bool(single.get("verified")),
        "sent": bool(single.get("sent")),
        "verification_strategy": single.get("verification_strategy"),
        "verification_elapsed_ms": single.get("verification_elapsed_ms"),
        "blocking_reasons": single.get("blocking_reasons") or [],
        "error_type": single.get("error_type"),
        "error_message": single.get("error"),
        "reply_result_path": (payload.get("paths") or {}).get("reply_result_json"),
    }


def write_batch_result_files(result: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "batch_reply_result.json"
    html_path = output / "batch_reply_report.html"
    result.setdefault("paths", {})
    result["paths"].update({"batch_reply_result_json": str(json_path), "batch_reply_report_html": str(html_path)})
    write_json(json_path, result)
    html_path.write_text(render_batch_report_html(result), encoding="utf-8")
    write_json(json_path, result)
    return result["paths"]


def select_acceptance_subset(plan: dict[str, Any], *, acceptance_max: int) -> list[dict[str, Any]]:
    acceptance_max = resolve_acceptance_max(acceptance_max)
    selected = [item for item in plan.get("items", []) if item.get("selected")]
    return selected[:acceptance_max]


def build_batch_acceptance_preconditions(
    plan_path: str | Path,
    plan: dict[str, Any] | None,
    *,
    acceptance_test: bool,
    acceptance_max: int,
    daily_limit: int,
    history_path: str | Path,
    execute: bool,
    confirm_send: bool,
    confirmed: bool,
    preflight_only: bool = False,
    json_valid: bool = True,
) -> list[dict[str, Any]]:
    selected = [item for item in (plan or {}).get("items", []) if item.get("selected")]
    subset = selected[: min(acceptance_max, len(selected))] if acceptance_test else selected
    daily_remaining = max(daily_limit - count_today_verified_replies(history_path), 0)
    unverified_lock = any(
        "unverified_previous_attempt" in (item.get("blocking_reasons") or [])
        for item in (plan or {}).get("items", [])
    )
    confirmation_required = execute and not preflight_only
    return [
        _precondition("Plan loaded", Path(plan_path).exists() and plan is not None and json_valid),
        _precondition("Plan JSON valid", json_valid),
        _precondition("Plan ID present", bool((plan or {}).get("plan_id"))),
        _precondition("Selected leads available", len(selected) > 0),
        _precondition("Acceptance subset <= 2", not acceptance_test or len(subset) <= DEFAULT_ACCEPTANCE_MAX),
        _precondition("Daily limit available", daily_remaining > 0),
        _precondition("No batch-level unverified lock", not unverified_lock),
        _precondition("Execute flag present", (not confirmation_required) or execute),
        _precondition("Confirm-send flag present", (not confirmation_required) or confirm_send),
        _precondition("Human confirmation present", (not confirmation_required) or confirmed),
    ]


def print_batch_acceptance_preconditions(preconditions: list[dict[str, Any]]) -> None:
    print("=== Phase 5.2 Batch Acceptance Preconditions ===")
    for item in preconditions:
        marker = "PASS" if item["pass"] else "FAIL"
        print(f"[{marker}] {item['name']}")
    if not all(item["pass"] for item in preconditions):
        print("BATCH ACCEPTANCE BLOCKED")


def print_batch_acceptance_preview(
    plan_path: str | Path,
    plan: dict[str, Any],
    *,
    acceptance_subset: list[dict[str, Any]],
    daily_verified_before: int,
    daily_remaining: int,
    interval_seconds: float,
    batch_mode: str = "acceptance_review",
) -> None:
    if batch_mode == "acceptance_execute":
        print("=== Phase 5.3 REAL BATCH ACCEPTANCE ===")
    else:
        print("=== Phase 5.2 Batch Acceptance Preview ===")
    print(f"Plan ID:\n{plan.get('plan_id') or ''}")
    print(f"Plan path:\n{plan_path}")
    if batch_mode == "acceptance_execute":
        print("Batch mode:\nacceptance_execute")
        print(f"Acceptance Max:\n{len(acceptance_subset)}")
    print(f"Selected in original plan:\n{sum(1 for item in plan.get('items', []) if item.get('selected'))}")
    print(f"Acceptance subset:\n{len(acceptance_subset)}")
    if batch_mode == "acceptance_execute":
        print("Subset:")
        for index, item in enumerate(acceptance_subset, start=1):
            print(f"{index}. {item.get('author_name') or ''}")
    print(f"Daily verified before:\n{daily_verified_before}")
    print(f"Daily remaining:\n{daily_remaining}")
    print(f"Interval:\n{interval_seconds} seconds")
    for index, item in enumerate(acceptance_subset, start=1):
        print(f"#{index}")
        print(f"Author:\n{item.get('author_name') or ''}")
        print(f"Comment:\n{item.get('comment_text') or ''}")
        print(f"Confidence:\n{item.get('llm_confidence')}")
        print(f"LLM reason:\n{item.get('llm_reason_zh') or ''}")
        print(f"Reply:\n{item.get('suggested_reply') or ''}")
        print(f"Direct comment URL:\n{item.get('direct_comment_url') or ''}")
        print(f"Idempotency key:\n{item.get('idempotency_key') or ''}")
    if batch_mode == "acceptance_execute":
        print("THIS COMMAND MAY SEND UP TO 2 REAL FACEBOOK REPLIES")
    else:
        print("THIS ACCEPTANCE TEST MAY SEND UP TO 2 REAL FACEBOOK REPLIES")


def print_acceptance_readiness(result: dict[str, Any]) -> None:
    if not result.get("acceptance_test") or result.get("execution_mode") != "preflight_only":
        return
    print("=== Phase 5.2 Acceptance Readiness ===")
    print(f"Subset count: {result.get('acceptance_subset_count')}")
    for item in result.get("results", []):
        print(f"{item.get('author_name')}:")
        print(f"Preflight: {'PASS' if item.get('preflight_ok') else 'FAIL'}")
        print(f"Duplicate: {str(bool(item.get('already_replied'))).lower()}")
        print(f"Comment unique: {str(item.get('matched_count') == 1).lower()}")
    print(f"Ready for real batch acceptance:\n{'YES' if result.get('ready_for_real_batch_acceptance') else 'NO'}")


def build_blocked_acceptance_result(
    plan: dict[str, Any] | None,
    *,
    status: str,
    preconditions: list[dict[str, Any]],
    acceptance_max: int,
    daily_limit: int,
    history_path: str | Path,
    interval_seconds: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    started_at = now or datetime.now(timezone.utc)
    selected = [item for item in (plan or {}).get("items", []) if item.get("selected")]
    subset = selected[: min(resolve_acceptance_max(acceptance_max), len(selected))]
    daily_before = count_today_verified_replies(history_path, now=started_at)
    result = {
        "batch_id": f"batch_{started_at.strftime('%Y%m%d_%H%M%S')}",
        "plan_id": (plan or {}).get("plan_id"),
        "status": status,
        "execution_mode": "acceptance_execute" if status == "cancelled" else "preflight_only",
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": _elapsed_ms(started_at),
        "planned_count": len(selected),
        "plan_selected_count": len(selected),
        "acceptance_test": True,
        "acceptance_max": acceptance_max,
        "acceptance_subset_count": len(subset),
        "acceptance_subset_plan_indexes": [item.get("plan_index") for item in subset],
        "attempted_count": 0,
        "verified_count": 0,
        "duplicate_count": 0,
        "blocked_count": 0,
        "unverified_count": 0,
        "failed_count": 0,
        "send_failed_count": 0,
        "total_send_action_count": 0,
        "preflight_passed_count": 0,
        "preflight_failed_count": 0,
        "ready_for_real_batch_acceptance": False,
        "daily_limit": daily_limit,
        "daily_verified_before": daily_before,
        "daily_verified_after": daily_before,
        "daily_remaining": max(daily_limit - daily_before, 0),
        "interval_seconds": interval_seconds,
        "batch_unverified_lock": _has_batch_unverified_lock(plan or {}),
        "acceptance_preconditions": preconditions,
        "batch_safety": _initial_batch_safety(),
        "results": [],
    }
    _refresh_batch_safety(result)
    _refresh_acceptance_readiness(result)
    return result


def count_today_verified_replies(history_path: str | Path, *, now: datetime | None = None) -> int:
    path = Path(history_path)
    if not path.exists():
        return 0
    today = (now or datetime.now(timezone.utc)).date()
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("verified") is not True or item.get("sent") is not True:
            continue
        try:
            stamped = datetime.fromisoformat(str(item.get("timestamp")).replace("Z", "+00:00")).date()
        except ValueError:
            continue
        if stamped == today:
            count += 1
    return count


def render_batch_plan_html(plan: BatchPlan) -> str:
    rows = "\n".join(_render_plan_item(item) for item in plan.items)
    review = _render_phase5_1_review(getattr(plan, "phase5_1_review", {}) or {})
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Facebook 批量回复计划</title>{_style()}</head>
<body><main>
<header><h1>Facebook 批量回复计划</h1><p>{_safety_note()}</p></header>
{review}
<section class="metrics">
{_metric("总候选", plan.summary["total_leads"])}
{_metric("可发送", plan.summary["eligible_count"])}
{_metric("已选择", plan.summary["selected_count"])}
{_metric("已回复", plan.summary["already_replied_count"])}
{_metric("被阻止", plan.summary["blocked_count"])}
{_metric("计划最大发送数", plan.max_leads)}
{_metric("最低置信度", plan.min_confidence)}
{_metric("每日剩余额度", plan.daily_remaining)}
{_metric("Target Policy", plan.summary.get("target_policy"))}
{_metric("允许回复 Lead", plan.summary.get("reply_allowed_count"))}
{_metric("仅发现不可回复 Lead", plan.summary.get("discovery_only_blocked_count"))}
</section>
<section><h2>审核清单</h2>{rows}</section>
</main>{_copy_script()}</body></html>"""


def render_enriched_lead_report_html(report: dict[str, Any]) -> str:
    review = _render_phase5_1_review(report.get("phase5_1_review") or {})
    rows = []
    for index, lead in enumerate(_ordered_report_leads(report), start=1):
        rows.append(
            f"""<article class="card">
<h3>#{index} {_e(lead.get('author_name'))}</h3>
<p class="comment">{_e(lead.get('comment_text'))}</p>
<p>规则判断：{_e(lead.get('rule_intent_level') or lead.get('intent_level'))}<br>
AI Review 来源：{_e(_review_source_label(lead.get('llm_review_source') or _llm_review_source_for_lead(lead)))}<br>
AI 状态：{_e(_lead_llm_status(lead))}<br>
AI 判断：{_e((lead.get('llm_review') or {}).get('is_lead'))}<br>
AI 置信度：{_e((lead.get('llm_review') or {}).get('confidence'))}<br>
AI 理由：{_e((lead.get('llm_review') or {}).get('reason_zh') or lead.get('final_reason_zh'))}</p>
<p class="reply">{_e((lead.get('llm_review') or {}).get('suggested_reply') or lead.get('final_suggested_reply'))}</p>
</article>"""
        )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Facebook Leads Enriched Report</title>{_style()}</head>
<body><main><header><h1>Facebook Leads Enriched Report</h1><p>Phase 5.1 AI 补审结果，不包含任何真实发送动作。</p></header>
{review}<section><h2>线索补审明细</h2>{''.join(rows)}</section></main>{_copy_script()}</body></html>"""


def render_batch_report_html(result: dict[str, Any]) -> str:
    rows = "\n".join(_render_result_item(item) for item in result.get("results", []))
    header_class = _status_class(result.get("status"))
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Facebook 批量回复执行报告</title>{_style()}</head>
<body><main>
<header class="{header_class}"><h1>Facebook 批量回复执行报告</h1><p>{_safety_note()}</p></header>
{_render_acceptance_execution_summary(result)}
<section class="metrics">
{_metric("Batch ID", result.get("batch_id"))}
{_metric("Plan ID", result.get("plan_id"))}
{_metric("批次状态", result.get("status"))}
{_metric("Acceptance Test", result.get("acceptance_test"))}
{_metric("Acceptance Max", result.get("acceptance_max"))}
{_metric("Plan Selected Count", result.get("plan_selected_count", result.get("planned_count")))}
{_metric("Acceptance Subset Count", result.get("acceptance_subset_count"))}
{_metric("Attempted", result.get("attempted_count"))}
{_metric("Verified", result.get("verified_count"))}
{_metric("真实发送成功", result.get("verified_count"))}
{_metric("Duplicate", result.get("duplicate_count"))}
{_metric("Blocked", result.get("blocked_count"))}
{_metric("Send Failed", result.get("send_failed_count", result.get("failed_count")))}
{_metric("Unverified", result.get("unverified_count"))}
{_metric("Preflight Passed", result.get("preflight_passed_count"))}
{_metric("Preflight Failed", result.get("preflight_failed_count"))}
{_metric("Ready For Real Batch", result.get("ready_for_real_batch_acceptance"))}
{_metric("Daily Verified Before", result.get("daily_verified_before"))}
{_metric("Daily Verified After", result.get("daily_verified_after"))}
{_metric("Daily Limit", result.get("daily_limit"))}
{_metric("Total Send Actions", result.get("total_send_action_count"))}
{_metric("Total Elapsed", result.get("elapsed_ms"))}
{_metric("Interval", result.get("interval_seconds"))}
</section>
<section><p>Start Time：{_e(result.get("started_at"))}<br>Finish Time：{_e(result.get("finished_at"))}</p></section>
{_render_batch_safety(result)}
<section><h2>执行明细</h2>{rows}</section>
</main>{_copy_script()}</body></html>"""


def _render_plan_item(item: dict[str, Any]) -> str:
    reason_labels = ", ".join(_blocking_reason_label(reason) for reason in item.get("blocking_reasons") or [])
    return f"""<article class="card {_status_class('planned' if item.get('selected') else 'blocked')}">
<h3>#{item.get('plan_index')} {_e(item.get('author_name'))}</h3>
<p class="comment">{_e(item.get('comment_text'))}</p>
<p>规则判断：{_e(item.get('rule_intent_level'))}　AI 判断：{_e(item.get('llm_is_lead'))}　AI 置信度：{_e(item.get('llm_confidence'))}</p>
<p>AI Review 来源：{_e(_review_source_label(item.get('llm_review_source')))}<br>AI 状态：{_e(item.get('llm_review_status'))}<br>AI 判断理由：{_e(item.get('llm_reason_zh'))}</p>
<p>来源归属：{_e(item.get('ownership_status'))}<br>允许回复：{_e(item.get('reply_allowed'))}<br>Target Policy：{_e(item.get('target_policy'))}<br>Ownership Reason：{_e(item.get('ownership_reason'))}</p>
<p>幂等状态：{_e(item.get('idempotency_key'))}<br>是否可发送：{_e(item.get('eligible'))}　是否已选择：{_e(item.get('selected'))}<br>阻止原因：{_e(reason_labels)}</p>
<p class="reply">{_e(item.get('suggested_reply'))}</p>
<p><button data-copy="{_attr(item.get('suggested_reply'))}" onclick="copyText(this)">复制建议回复</button>
<a href="{_attr(item.get('source_content_url'))}" target="_blank">打开原帖</a>
<a href="{_attr(item.get('direct_comment_url'))}" target="_blank">查看原评论</a></p>
</article>"""


def _render_result_item(item: dict[str, Any]) -> str:
    preflight_status = "PASS" if item.get("preflight_ok") else "FAIL"
    send_summary = (
        "Not attempted"
        if item.get("execution_mode") == "preflight_only"
        else f"send_action_performed={_e(item.get('send_action_performed'))} / send_action_count={_e(item.get('send_action_count'))} / sent={_e(item.get('sent'))}"
    )
    verification_summary = (
        "N/A"
        if item.get("execution_mode") == "preflight_only"
        else f"verified={_e(item.get('verified'))} / strategy={_e(item.get('verification_strategy'))} / elapsed_ms={_e(item.get('verification_elapsed_ms'))}"
    )
    return f"""<article class="card {_status_class(item.get('status'))}">
<h3>#{item.get('plan_index')} {_e(item.get('author_name'))} <span>{_e(_status_label(item.get('status')))}</span></h3>
<p class="comment">{_e(item.get('comment_text'))}</p>
<p class="reply">{_e(item.get('reply_text'))}</p>
<p>LLM Confidence：{_e(item.get('llm_confidence'))}<br>LLM Reason：{_e(item.get('llm_reason_zh'))}</p>
<p>Status：{_e(_status_label(item.get('status')))}<br>Stage：{_e(item.get('stage'))}<br>Execution Mode：{_e(item.get('execution_mode'))}</p>
<p>Preflight：{_e(preflight_status)}<br>Comment Locate：{_e(item.get('locate_strategy'))} / matched_count={_e(item.get('matched_count'))}</p>
<p>Reply Composer：found={_e(item.get('reply_composer_found'))} / strategy={_e(item.get('reply_composer_strategy'))} / send matched count={_e(item.get('composer_send_action_matched_count'))}</p>
<p>Page Obstruction：<br>
Detected：{_e(item.get('obstruction_detected'))}<br>
Types：{_e(', '.join(item.get('obstruction_types') or []))}<br>
Dismiss Attempted：{_e(item.get('obstruction_dismiss_attempted'))}<br>
Dismissed Count：{_e(item.get('obstruction_dismissed_count'))}<br>
Reply Click Attempts：{_e(item.get('reply_click_attempts'))}<br>
Recovered：{_e(item.get('reply_click_recovered'))}</p>
<p>Preflight Diagnostics：lead_found={_e(item.get('lead_found'))} / comment_located={_e(item.get('comment_located'))} / reply_action_found={_e(item.get('reply_action_found'))}<br>
reply_input_found={_e(item.get('reply_input_found'))} / reply_text_present={_e(item.get('reply_text_present'))} / already_replied={_e(item.get('already_replied'))}<br>
page_state_valid={_e(item.get('page_state_valid'))} / send_allowed={_e(item.get('send_allowed'))} / send_action_checked={_e(item.get('send_action_checked'))}</p>
<p>Send：{send_summary}</p>
<p>Verification：{verification_summary}</p>
<p>Blocking Reasons：{_e(', '.join(item.get('blocking_reasons') or []))}<br>Error Type：{_e(item.get('error_type'))}<br>Error Message：{_e(item.get('error_message'))}<br>reply_result.json：{_e(item.get('reply_result_path'))}</p>
<p><a href="{_attr(item.get('source_content_url'))}" target="_blank">打开原帖</a><a href="{_attr(item.get('direct_comment_url'))}" target="_blank">查看原评论</a></p>
</article>"""


def _increment_result_counts(result: dict[str, Any], entry: dict[str, Any]) -> None:
    status = entry.get("status")
    if status == "verified" and entry.get("sent") and entry.get("verified"):
        result["verified_count"] += 1
    elif status == "duplicate":
        result["duplicate_count"] += 1
    elif status == "blocked":
        result["blocked_count"] += 1
    elif status == "unverified":
        result["unverified_count"] += 1
    elif status in {"send_failed", "failed"}:
        result["failed_count"] += 1
        if status == "send_failed":
            result["send_failed_count"] += 1


def _batch_stop_status(entry: dict[str, Any]) -> str | None:
    if entry.get("send_action_count", 0) > 1:
        return "failed"
    if entry.get("status") in STOP_STATUSES:
        return "stopped_unverified"
    if entry.get("error_type") in STOP_ERROR_TYPES:
        return "failed"
    reasons = set(entry.get("blocking_reasons") or [])
    if any("login state blocks send" in str(reason) or "page_state" in str(reason) for reason in reasons):
        return "stopped_login"
    if entry.get("error_type") in {"BrowserDisconnectedError", "TargetClosedError"}:
        return "stopped_browser"
    return None


def _source_not_allowed_payload(request: ReplyRequest) -> dict[str, Any]:
    return {
        "request": request.to_dict(),
        "result": {
            "success": False,
            "stage": "source_ownership_guard",
            "status": "blocked",
            "send_action_performed": False,
            "sent": False,
            "verified": False,
            "dry_run": False,
            "blocking_reasons": ["source_not_allowed"],
            "error_type": "source_not_allowed",
            "error": "Source ownership policy does not allow replying to this lead",
        },
        "diagnostics": {
            "send_action_count": 0,
            "target_policy": request.target_policy,
            "ownership_status": request.ownership_status,
            "reply_allowed": request.reply_allowed,
        },
        "paths": {},
    }


def _exception_payload(request: ReplyRequest, exc: Exception) -> dict[str, Any]:
    return {
        "request": request.to_dict(),
        "result": {
            "status": "failed",
            "send_action_performed": False,
            "sent": False,
            "verified": False,
            "blocking_reasons": [],
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        },
        "diagnostics": {"send_action_count": 0},
        "paths": {},
    }


def _initial_batch_safety() -> dict[str, Any]:
    return {
        "unverified_occurred": False,
        "browser_disconnected": False,
        "login_lost": False,
        "daily_limit_triggered": False,
        "send_action_count_gt_one": False,
        "batch_breaker_triggered": False,
        "total_send_action_count": 0,
        "verified_count": 0,
    }


def _execution_mode(config: BatchExecuteConfig) -> str:
    if config.preflight_only:
        return "preflight_only"
    if config.dry_run:
        return "dry_run"
    if config.acceptance_test and config.execute:
        return "acceptance_execute"
    if config.execute:
        return "execute"
    return "dry_run"


def _preflight_diagnostics(
    item: dict[str, Any],
    single: dict[str, Any],
    diagnostics: dict[str, Any],
    preflight: dict[str, Any],
    execution_mode: str,
) -> dict[str, Any]:
    blocking_reasons = single.get("blocking_reasons") or []
    matched_count = single.get("matched_count") if single.get("matched_count") is not None else preflight.get("matched_count")
    comment_located = bool(single.get("located")) or matched_count == 1
    reply_text_present = bool((single.get("reply_text") or item.get("suggested_reply") or "").strip())
    reply_input_found = bool(single.get("input_found"))
    page_state_valid = bool(preflight.get("page_state_valid", True)) and not any(
        "page_state" in str(reason) or "login state blocks send" in str(reason) for reason in blocking_reasons
    )
    if "ok" in preflight:
        preflight_ok = bool(preflight.get("ok"))
    else:
        preflight_ok = bool(
            comment_located
            and reply_input_found
            and reply_text_present
            and page_state_valid
            and not blocking_reasons
            and single.get("error_type") is None
        )
    return {
        "preflight_ok": preflight_ok,
        "lead_found": comment_located,
        "comment_located": comment_located,
        "reply_action_found": bool(single.get("reply_clicked")) if single.get("reply_clicked") is not None else comment_located,
        "reply_input_found": reply_input_found,
        "reply_text_present": reply_text_present,
        "already_replied": bool(single.get("already_replied") or preflight.get("already_replied")),
        "page_state_valid": page_state_valid,
        "send_allowed": bool(preflight.get("ok")) if preflight else (preflight_ok and execution_mode not in {"preflight_only", "dry_run"}),
        "send_action_checked": execution_mode not in {"preflight_only"} and diagnostics.get("send_action_count") is not None,
    }


def _batch_item_status(single: dict[str, Any], preflight_diag: dict[str, Any], execution_mode: str) -> str:
    if single.get("status") in {"duplicate", "blocked_unverified_previous_attempt"}:
        return str(single.get("status"))
    if execution_mode == "preflight_only":
        return "preflight_passed" if preflight_diag.get("preflight_ok") else "preflight_failed"
    return str(single.get("status") or "failed")


def _refresh_preflight_counts(result: dict[str, Any]) -> None:
    result["preflight_passed_count"] = sum(1 for item in result.get("results", []) if item.get("status") == "preflight_passed")
    result["preflight_failed_count"] = sum(1 for item in result.get("results", []) if item.get("status") == "preflight_failed")


def _refresh_acceptance_readiness(result: dict[str, Any]) -> None:
    result["ready_for_real_batch_acceptance"] = bool(
        result.get("acceptance_test") is True
        and result.get("execution_mode") == "preflight_only"
        and int(result.get("acceptance_subset_count") or 0) > 0
        and len(result.get("results", [])) == int(result.get("acceptance_subset_count") or 0)
        and all(item.get("preflight_ok") is True for item in result.get("results", []))
        and not result.get("batch_unverified_lock")
        and int(result.get("daily_remaining") or 0) > 0
    )


def _has_batch_unverified_lock(plan: dict[str, Any]) -> bool:
    return any(
        "unverified_previous_attempt" in (item.get("blocking_reasons") or [])
        for item in plan.get("items", [])
    )


def _refresh_batch_safety(result: dict[str, Any]) -> None:
    statuses = {item.get("status") for item in result.get("results", [])}
    error_types = {item.get("error_type") for item in result.get("results", [])}
    blocking = [reason for item in result.get("results", []) for reason in item.get("blocking_reasons") or []]
    total_send_actions = sum(int(item.get("send_action_count") or 0) for item in result.get("results", []))
    safety = result.setdefault("batch_safety", _initial_batch_safety())
    safety.update(
        {
            "unverified_occurred": "unverified" in statuses or result.get("status") == "stopped_unverified",
            "browser_disconnected": bool(error_types & {"BrowserDisconnectedError", "TargetClosedError"})
            or result.get("status") == "stopped_browser",
            "login_lost": any("login state blocks send" in str(reason) or "page_state" in str(reason) for reason in blocking)
            or result.get("status") == "stopped_login",
            "daily_limit_triggered": result.get("status") == "daily_limit_reached",
            "send_action_count_gt_one": any(int(item.get("send_action_count") or 0) > 1 for item in result.get("results", [])),
            "batch_breaker_triggered": result.get("status") in {"stopped_unverified", "stopped_login", "stopped_browser", "failed"},
            "total_send_action_count": total_send_actions,
            "verified_count": result.get("verified_count", 0),
        }
    )


def _elapsed_ms(started_at: datetime) -> int:
    return int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)


def _precondition(name: str, passed: bool) -> dict[str, Any]:
    return {"name": name, "pass": bool(passed)}


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _lead_llm_status(lead: dict[str, Any]) -> str | None:
    review = lead.get("llm_review") or {}
    return lead.get("llm_review_status") or review.get("status")


def _llm_review_source_for_lead(lead: dict[str, Any]) -> str:
    status = _lead_llm_status(lead)
    if status == "success":
        return lead.get("llm_review_source") or "existing"
    return lead.get("llm_review_source") or "not_reviewed"


def _review_attempt_source(status: str | None) -> str:
    if status == "failed":
        return "phase5_1_retry_failed"
    if status == "timeout":
        return "phase5_1_retry_timeout"
    return "phase5_1_missing_review"


def _resolve_positive_int(value: int | None, env_name: str, default: int, env: dict[str, str] | None) -> int:
    if value is not None:
        resolved = int(value)
    else:
        raw = (env or os.environ).get(env_name)
        resolved = int(raw) if raw else default
    if resolved < 1:
        raise ValueError(f"{env_name} must be >= 1")
    return resolved


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _render_phase5_1_review(review: dict[str, Any]) -> str:
    if not review:
        return ""
    return f"""<section class="review">
<h2>Phase 5.1 AI 补审摘要</h2>
<div class="metrics">
{_metric("已有 AI 结果", review.get("existing_success_count"))}
{_metric("本次待补审", review.get("missing_count"))}
{_metric("本次补审", review.get("requested_count"))}
{_metric("补审成功", review.get("success_count"))}
{_metric("补审 fallback", review.get("fallback_count"))}
{_metric("历史已回复", review.get("verified_history_count"))}
{_metric("因已回复跳过 AI 补审", review.get("verified_skipped_from_review_count", review.get("verified_skipped_count")))}
{_metric("LLM 模型", review.get("model"))}
{_metric("LLM 调用次数", review.get("call_count"))}
{_metric("Tokens", review.get("total_tokens"))}
{_metric("耗时 ms", review.get("elapsed_ms"))}
</div>
<p>Prompt：{_e(review.get("prompt_version"))}</p>
</section>"""


def _render_acceptance_execution_summary(result: dict[str, Any]) -> str:
    if not result.get("acceptance_test"):
        return ""
    return f"""<section class="review">
<h2>Phase 5.2 Acceptance 执行摘要</h2>
<p>本次为 Phase 5.2 真实批量验收。</p>
<p>原始 Plan 选中 {_e(result.get('plan_selected_count', result.get('planned_count')))} 条。验收模式最多处理 {_e(result.get('acceptance_max'))} 条。
实际处理 {_e(result.get('attempted_count'))} 条。实际真实发送 {_e(result.get('total_send_action_count'))} 条。verified {_e(result.get('verified_count'))} 条。
Preflight Passed：{_e(result.get('preflight_passed_count'))} 条。Preflight Failed：{_e(result.get('preflight_failed_count'))} 条。</p>
</section>"""


def _render_batch_safety(result: dict[str, Any]) -> str:
    safety = result.get("batch_safety") or {}
    return f"""<section class="review">
<h2>Batch Safety Summary</h2>
<div class="metrics">
{_metric("是否发生 unverified", safety.get("unverified_occurred"))}
{_metric("是否发生 browser disconnect", safety.get("browser_disconnected"))}
{_metric("是否发生 login lost", safety.get("login_lost"))}
{_metric("是否触发 daily limit", safety.get("daily_limit_triggered"))}
{_metric("send_action_count > 1", safety.get("send_action_count_gt_one"))}
{_metric("是否触发 batch breaker", safety.get("batch_breaker_triggered"))}
{_metric("真实 send action 总次数", safety.get("total_send_action_count"))}
{_metric("verified 成功数", safety.get("verified_count"))}
{_metric("Preflight Passed", result.get("preflight_passed_count"))}
{_metric("Preflight Failed", result.get("preflight_failed_count"))}
</div>
</section>"""


def _blocking_reason_label(reason: str) -> str:
    return {
        "duplicate_history": "已存在成功回复记录",
        "llm_review_not_success": "AI 复核未成功",
        "llm_not_lead": "AI 判断不是潜客",
        "llm_should_reply_false": "AI 建议不回复",
        "suggested_reply_empty": "缺少建议回复",
        "confidence_below_threshold": "AI 置信度低于阈值",
        "unverified_previous_attempt": "存在未确认发送记录",
        "comment_locator_missing": "缺少可定位评论链接",
        "source_not_allowed": "来源不允许回复",
    }.get(reason, reason)


def _review_source_label(source: Any) -> str:
    return {
        "existing": "已有 AI 结果",
        "phase5_1_reviewed": "Phase 5.1 补审",
        "phase5_1_fallback": "Phase 5.1 fallback",
        "not_reviewed": "未补审",
    }.get(str(source or ""), str(source or ""))


def _style() -> str:
    return """<style>
body{margin:0;background:#f4f6f8;color:#17202a;font-family:Arial,"Microsoft YaHei",sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px}header{background:#17202a;color:white;border-radius:8px;padding:24px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}.metric,.card{background:white;border:1px solid #d8dee6;border-radius:8px;padding:14px}
.metric strong{display:block;font-size:24px}.card{margin:12px 0}.comment,.reply{white-space:pre-wrap;background:#f8fafc;border-left:4px solid #94a3b8;padding:10px}
.status-verified{border-left:6px solid #15803d}.status-duplicate{border-left:6px solid #64748b}.status-blocked{border-left:6px solid #ca8a04}
.status-send-failed,.status-failed{border-left:6px solid #dc2626}.status-unverified,.status-stopped-unverified{border-left:6px solid #7f1d1d}.status-planned{border-left:6px solid #64748b}
.status-preflight-passed{border-left:6px solid #22c55e}.status-preflight-failed{border-left:6px solid #ca8a04}
.status-stopped-login,.status-stopped-browser{border-left:6px solid #dc2626}
a,button{margin-right:10px}</style>"""


def _safety_note() -> str:
    return (
        "本报告展示受控批量回复。真实发送仅在 --execute + --confirm-send + 人工确认 SEND BATCH 全部满足后执行。"
        "每条回复仍独立进行唯一定位、重复检测、Preflight、发送后验证。发生 unverified 时整个批次立即停止。"
    )


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><strong>{_e(value)}</strong>{_e(label)}</div>"


def _status_class(status: Any) -> str:
    return "status-" + str(status or "planned").replace("_", "-")


def _status_label(status: Any) -> str:
    return {
        "preflight_passed": "Preflight Passed",
        "preflight_failed": "Preflight Failed",
    }.get(str(status or ""), str(status or ""))


def _copy_script() -> str:
    return """<script>function copyText(b){navigator.clipboard.writeText(b.getAttribute('data-copy')||'');b.innerText='已复制';setTimeout(()=>b.innerText='复制建议回复',1200);}</script>"""


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _attr(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)
