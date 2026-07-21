from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

try:  # noqa: E402
    from facebook_readonly_scan import run_cli_scan
except ModuleNotFoundError:  # noqa: E402
    from scripts.facebook_readonly_scan import run_cli_scan
from src.facebook_leads.browser_adapter import (  # noqa: E402
    BrowserCdpNotConfiguredError,
)
from src.facebook_leads.facebook.report import (  # noqa: E402
    build_lead_report,
    write_lead_report_files,
)
from src.facebook_leads.facebook.llm_review import (  # noqa: E402
    apply_review_to_leads,
    build_facebook_leads_llm_client,
    build_llm_review_summary,
    review_leads_with_llm_detailed,
    resolve_llm_concurrency,
    resolve_llm_timeout_seconds,
)


async def run_lead_scan(args: argparse.Namespace) -> dict:
    started = time.perf_counter()
    llm_client = getattr(args, "llm_client", None)
    if args.llm_review and llm_client is None:
        llm_client = build_facebook_leads_llm_client(model_name=args.llm_model)
    llm_concurrency = resolve_llm_concurrency(getattr(args, "llm_concurrency", None)) if args.llm_review else None
    llm_timeout_seconds = resolve_llm_timeout_seconds(getattr(args, "llm_timeout_seconds", None)) if args.llm_review else None
    readonly_args = argparse.Namespace(
        keyword=args.keyword,
        content_limit=args.content_limit,
        comment_limit=args.comment_limit,
        max_scrolls=args.max_scrolls,
        max_expand_clicks=args.max_expand_clicks,
        current_page_only=args.current_page_only,
        output=None,
        artifacts_dir=args.output_dir,
    )
    scan_payload = await run_cli_scan(readonly_args)
    report = build_lead_report(scan_payload)
    llm_review_payload = None
    if args.llm_review:
        all_leads = [lead for content in report.contents for lead in content.leads]
        llm_review_payload = await review_leads_with_llm_detailed(
            all_leads,
            batch_size=args.llm_batch_size,
            llm_client=llm_client,
            model_name=args.llm_model,
            concurrency=llm_concurrency,
            timeout_seconds=llm_timeout_seconds,
        )
        reviewed_leads = apply_review_to_leads(all_leads, llm_review_payload["reviewed"])
        lead_index = 0
        for content in report.contents:
            count = len(content.leads)
            content.leads = reviewed_leads[lead_index : lead_index + count]
            lead_index += count
        report.timing.update(llm_review_payload["timing"])
        report.llm_review = llm_review_payload["summary"]
    else:
        report.llm_review = build_llm_review_summary(
            enabled=False,
            model=args.llm_model,
            candidate_count=report.lead_candidate_count,
            batches=[],
            batch_size=args.llm_batch_size,
            concurrency=None,
            elapsed_ms=0,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
        )
    artifact_dir = Path(scan_payload["diagnostics"]["artifact_dir"])
    report_paths = write_lead_report_files(report, artifact_dir)
    payload = {
        "success": bool(scan_payload.get("success")),
        "scan": scan_payload,
        "lead_report": report.to_dict(),
        "paths": {
            "result_json": scan_payload["diagnostics"].get("result_path"),
            **report_paths,
        },
        "timing": {
            **report.timing,
            "lead_scan_total_ms": int((time.perf_counter() - started) * 1000),
        },
        "diagnostics": {
            "read_only": True,
            "no_facebook_write_operations": True,
            "llm_called": bool(args.llm_review),
            "llm_review": (llm_review_payload or {}).get("diagnostics"),
            "agent_called": False,
            "closed_remote_chromium": scan_payload["diagnostics"].get("closed_remote_chromium", False),
            "close_called": scan_payload["diagnostics"].get("close_called", False),
        },
    }
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Facebook lead intent scan with local rules and HTML report generation."
    )
    parser.add_argument("--keyword", default=None)
    parser.add_argument("--content-limit", type=int, default=5)
    parser.add_argument("--comment-limit", type=int, default=100)
    parser.add_argument("--max-scrolls", type=int, default=5)
    parser.add_argument("--max-expand-clicks", type=int, default=20)
    parser.add_argument("--output-dir", default="artifacts/facebook_leads")
    parser.add_argument("--output", default=None)
    parser.add_argument("--llm-review", action="store_true", help="Review rule-based lead candidates with an LLM.")
    parser.add_argument("--llm-batch-size", type=int, default=10)
    parser.add_argument("--llm-model", default=None, help="Temporary model override for Facebook Leads LLM review.")
    parser.add_argument("--llm-concurrency", type=int, default=None)
    parser.add_argument("--llm-timeout-seconds", type=float, default=None)
    parser.add_argument(
        "--current-page-only",
        action="store_true",
        help="Build a lead report from the currently open Facebook content page.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        payload = asyncio.run(run_lead_scan(args))
    except BrowserCdpNotConfiguredError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    except ModuleNotFoundError as exc:
        if exc.name == "browser_use":
            raise SystemExit(
                "ERROR: browser-use is not installed in this Python environment"
            ) from exc
        raise
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
