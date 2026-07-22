from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from src.facebook_leads.facebook.diagnostics import write_json  # noqa: E402
from src.facebook_leads.facebook.intent_models import ContentLeadSummary, IntentMatch, LeadCandidate  # noqa: E402
from src.facebook_leads.facebook.llm_review import (  # noqa: E402
    review_leads_with_llm_detailed,
    resolve_llm_concurrency,
    resolve_llm_max_batch_chars,
    resolve_llm_timeout_seconds,
)
from src.facebook_leads.facebook.report import build_lead_report  # noqa: E402


def load_candidates(path: str | Path) -> list[LeadCandidate]:
    input_path = Path(path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if "lead_report" in payload:
        payload = payload["lead_report"]
    if "contents" in payload and any("leads" in item for item in payload.get("contents") or []):
        return _leads_from_report_dict(payload)
    return [lead for content in build_lead_report(payload).contents for lead in content.leads]


def _leads_from_report_dict(payload: dict[str, Any]) -> list[LeadCandidate]:
    leads: list[LeadCandidate] = []
    for content in payload.get("contents") or []:
        if not isinstance(content, dict):
            continue
        for raw in content.get("leads") or []:
            if isinstance(raw, dict):
                leads.append(_lead_from_dict(raw, content))
    return leads


def _lead_from_dict(raw: dict[str, Any], content: dict[str, Any]) -> LeadCandidate:
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


async def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    started = time.perf_counter()
    leads = load_candidates(args.input)
    if args.limit is not None:
        leads = leads[: args.limit]
    concurrency = resolve_llm_concurrency(args.concurrency)
    timeout_seconds = resolve_llm_timeout_seconds(args.timeout_seconds)
    max_batch_chars = resolve_llm_max_batch_chars(args.max_batch_chars)
    result = await review_leads_with_llm_detailed(
        leads,
        batch_size=args.batch_size,
        model_name=args.model,
        concurrency=concurrency,
        timeout_seconds=timeout_seconds,
        max_batch_chars=max_batch_chars,
    )
    summary = result["summary"]
    candidate_count = len(leads)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    total_tokens = summary.get("total_tokens")
    benchmark = {
        "model": summary.get("model") or args.model,
        "prompt_version": summary.get("prompt_version"),
        "candidate_count": candidate_count,
        "batch_count": len(result["diagnostics"]["batches"]),
        "batch_size": args.batch_size,
        "concurrency": concurrency,
        "timeout_seconds": timeout_seconds,
        "max_batch_chars": max_batch_chars,
        "success_count": summary.get("success_count"),
        "fallback_count": summary.get("fallback_count"),
        "call_count": summary.get("call_count"),
        "prompt_tokens": summary.get("prompt_tokens"),
        "completion_tokens": summary.get("completion_tokens"),
        "total_tokens": total_tokens,
        "elapsed_ms": elapsed_ms,
        "llm_elapsed_ms": summary.get("elapsed_ms"),
        "tokens_per_candidate": round(total_tokens / candidate_count, 2) if total_tokens is not None and candidate_count else None,
        "ms_per_candidate": round(elapsed_ms / candidate_count, 2) if candidate_count else None,
        "batches": result["diagnostics"]["batches"],
        "no_browser_started": True,
        "no_facebook_write_operations": True,
    }
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    write_json(output_path, benchmark)
    benchmark["output_json"] = str(output_path)
    return benchmark


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark Facebook Leads LLM review without browser or reply actions.")
    parser.add_argument("--input", required=True, help="Existing lead_report.json, lead_scan payload, or result.json.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("--max-batch-chars", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", default="artifacts/facebook_leads/benchmarks")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        payload = asyncio.run(run_benchmark(args))
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
