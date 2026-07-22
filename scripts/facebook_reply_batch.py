from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from src.facebook_leads.browser_adapter import (  # noqa: E402
    BrowserCdpNotConfiguredError,
    get_browser_window_size,
    require_browser_cdp,
    select_active_or_facebook_page,
)
from src.facebook_leads.facebook.reply import reply_to_comment  # noqa: E402
from src.facebook_leads.facebook.reply_batch import (  # noqa: E402
    BatchExecuteConfig,
    BatchPlanConfig,
    build_batch_acceptance_preconditions,
    build_blocked_acceptance_result,
    build_batch_plan,
    enrich_lead_report_missing_reviews,
    execute_batch_plan,
    print_batch_acceptance_preconditions,
    print_batch_acceptance_preview,
    print_acceptance_readiness,
    render_batch_plan_html,
    resolve_acceptance_max,
    resolve_batch_max,
    resolve_daily_limit,
    resolve_interval_seconds,
    select_acceptance_subset,
    write_batch_plan_files,
    write_batch_result_files,
)
from src.facebook_leads.facebook.target_policy import build_target_policy_config, target_policy_from_env  # noqa: E402


async def run_reply_batch(args: argparse.Namespace) -> dict:
    max_leads = resolve_batch_max(args.max_leads)
    daily_limit = resolve_daily_limit(args.daily_limit)
    interval_seconds = resolve_interval_seconds(args.interval_seconds)
    acceptance_max = resolve_acceptance_max(getattr(args, "acceptance_max", None))
    target_policy = _target_policy_from_args(args)
    if args.lead_report and args.plan_only:
        lead_report_path = Path(args.lead_report)
        if getattr(args, "review_missing", False):
            output_dir = Path(args.output_dir) if args.output_dir else lead_report_path.parent / "phase5_1"
            enrichment = await enrich_lead_report_missing_reviews(
                lead_report_path,
                output_dir=output_dir,
                history_path=args.history_path,
                batch_size=getattr(args, "llm_batch_size", 10),
                model_name=getattr(args, "llm_model", None),
                concurrency=getattr(args, "llm_concurrency", None),
                timeout_seconds=getattr(args, "llm_timeout_seconds", None),
                max_batch_chars=getattr(args, "llm_max_batch_chars", None),
                dry_run=getattr(args, "review_missing_dry_run", False),
            )
            enriched_path = enrichment["paths"]["lead_report_enriched_json"]
            if getattr(args, "review_missing_only", False):
                return {
                    "mode": "review_missing_only",
                    "phase5_1_review": enrichment["summary"],
                    "paths": enrichment["paths"],
                }
            plan = build_batch_plan(
                enriched_path,
                config=BatchPlanConfig(
                    max_leads=max_leads,
                    min_confidence=args.min_confidence,
                    daily_limit=daily_limit,
                    interval_seconds=interval_seconds,
                    history_path=args.history_path,
                    target_policy=target_policy,
                ),
            )
            paths = write_batch_plan_files(plan, output_dir)
            return {
                "mode": "review_missing_plan_only",
                "phase5_1_review": enrichment["summary"],
                "plan": plan.to_dict(),
                "paths": enrichment["paths"] | paths,
            }
        plan = build_batch_plan(
            lead_report_path,
            config=BatchPlanConfig(
                max_leads=max_leads,
                min_confidence=args.min_confidence,
                daily_limit=daily_limit,
                interval_seconds=interval_seconds,
                history_path=args.history_path,
                target_policy=target_policy,
            ),
        )
        paths = write_batch_plan_files(plan, args.output_dir or lead_report_path.parent)
        return {"mode": "plan_only", "plan": plan.to_dict(), "paths": paths}
    if args.plan:
        plan_path = Path(args.plan)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if not (args.execute or args.dry_run or args.preflight_only):
            html_path = Path(args.plan).with_suffix(".html")
            html_path.write_text(render_batch_plan_html(_plan_from_dict(plan)), encoding="utf-8")
            return {"mode": "plan_review", "plan": plan, "paths": {"batch_reply_plan_html": str(html_path)}}
        confirmed = bool(args.yes_batch)
        if args.execute and args.confirm_send and not confirmed:
            confirmed = confirm_batch_interactive()
        if getattr(args, "acceptance_test", False):
            preconditions = build_batch_acceptance_preconditions(
                plan_path,
                plan,
                acceptance_test=True,
                acceptance_max=acceptance_max,
                daily_limit=daily_limit,
                history_path=args.history_path,
                execute=args.execute,
                confirm_send=args.confirm_send,
                confirmed=confirmed,
                preflight_only=args.preflight_only,
            )
            print_batch_acceptance_preconditions(preconditions)
            subset = select_acceptance_subset(plan, acceptance_max=acceptance_max)
            daily_before = 0
            try:
                from src.facebook_leads.facebook.reply_batch import count_today_verified_replies

                daily_before = count_today_verified_replies(args.history_path)
            except Exception:
                daily_before = 0
            print_batch_acceptance_preview(
                plan_path,
                plan,
                acceptance_subset=subset,
                daily_verified_before=daily_before,
                daily_remaining=max(daily_limit - daily_before, 0),
                interval_seconds=interval_seconds,
                batch_mode="acceptance_execute" if args.execute else "acceptance_review",
            )
            if not all(item["pass"] for item in preconditions):
                result = build_blocked_acceptance_result(
                    plan,
                    status="cancelled" if args.execute else "blocked",
                    preconditions=preconditions,
                    acceptance_max=acceptance_max,
                    daily_limit=daily_limit,
                    history_path=args.history_path,
                    interval_seconds=interval_seconds,
                )
                paths = write_batch_result_files(result, args.output_dir or plan_path.parent)
                return {"mode": "acceptance_blocked", "result": result, "paths": paths}
        if args.execute and (not args.confirm_send or not confirmed):
            result = await execute_batch_plan(
                plan,
                config=BatchExecuteConfig(
                    execute=args.execute,
                    confirm_send=args.confirm_send,
                    confirmed=confirmed,
                    max_leads=max_leads,
                    daily_limit=daily_limit,
                    interval_seconds=interval_seconds,
                    history_path=args.history_path,
                    artifacts_dir=args.output_dir,
                    acceptance_test=getattr(args, "acceptance_test", False),
                    acceptance_max=acceptance_max,
                ),
            )
            paths = write_batch_result_files(result, args.output_dir or plan_path.parent)
            return {"mode": "execute", "result": result, "paths": paths}
        page = None
        if args.execute or args.dry_run or args.preflight_only:
            page = await get_active_facebook_page()

        async def runner(active_page, request):
            return await reply_to_comment(
                active_page,
                request,
                artifacts_dir=args.single_artifacts_dir,
                history_path=args.history_path,
            )

        result = await execute_batch_plan(
            plan,
            config=BatchExecuteConfig(
                execute=args.execute,
                confirm_send=args.confirm_send,
                confirmed=confirmed,
                dry_run=args.dry_run,
                preflight_only=args.preflight_only,
                max_leads=max_leads,
                daily_limit=daily_limit,
                interval_seconds=interval_seconds,
                history_path=args.history_path,
                artifacts_dir=args.output_dir,
                acceptance_test=getattr(args, "acceptance_test", False),
                acceptance_max=acceptance_max,
            ),
            page=page,
            reply_runner=runner,
            persist=lambda payload: write_batch_result_files(payload, args.output_dir or plan_path.parent),
        )
        paths = write_batch_result_files(result, args.output_dir or plan_path.parent)
        print_acceptance_readiness(result)
        return {"mode": "execute" if args.execute else "dry_run", "result": result, "paths": paths}
    raise ValueError("Use --lead-report --plan-only or --plan with --execute/--dry-run/--preflight-only")


async def get_active_facebook_page():
    cdp_url = require_browser_cdp()
    window_w, window_h = get_browser_window_size()
    from browser_use.browser.browser import BrowserConfig
    from browser_use.browser.context import BrowserContextConfig
    from src.browser.custom_browser import CustomBrowser

    browser = CustomBrowser(
        config=BrowserConfig(
            cdp_url=cdp_url,
            headless=False,
            keep_alive=True,
            new_context_config=BrowserContextConfig(keep_alive=True, window_width=window_w, window_height=window_h),
        )
    )
    browser_context = await browser.new_context(
        BrowserContextConfig(keep_alive=True, force_new_context=False, window_width=window_w, window_height=window_h)
    )
    return await select_active_or_facebook_page(browser_context)


def confirm_batch_interactive() -> bool:
    if not sys.stdin:
        print("Interactive confirmation unavailable. Type SEND BATCH in a terminal or use --yes-batch after reviewing the plan.")
        return False
    if not sys.stdin.isatty():
        return sys.stdin.read().strip() == "SEND BATCH"
    return input("Type SEND BATCH to confirm this batch: ").strip() == "SEND BATCH"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Controlled Facebook Leads batch safe reply planner and executor.")
    parser.add_argument("--lead-report", default=None)
    parser.add_argument("--plan", default=None)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--review-missing", action="store_true")
    parser.add_argument("--review-missing-only", action="store_true")
    parser.add_argument("--review-missing-dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--acceptance-test", action="store_true")
    parser.add_argument("--acceptance-max", type=int, default=None)
    parser.add_argument("--confirm-send", action="store_true")
    parser.add_argument("--yes-batch", action="store_true")
    parser.add_argument("--max-leads", type=int, default=None)
    parser.add_argument("--min-confidence", type=float, default=0.90)
    parser.add_argument("--daily-limit", type=int, default=None)
    parser.add_argument("--interval-seconds", type=float, default=None)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--history-path", default="artifacts/facebook_leads/reply_history.jsonl")
    parser.add_argument("--single-artifacts-dir", default="artifacts/facebook_leads/replies")
    parser.add_argument("--llm-batch-size", type=int, default=10)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-concurrency", type=int, default=None)
    parser.add_argument("--llm-timeout-seconds", type=float, default=None)
    parser.add_argument("--llm-max-batch-chars", type=int, default=None)
    parser.add_argument("--target-policy", choices=["owned_only", "allowlist", "discovery_only"], default=None)
    parser.add_argument("--allow-source-url", action="append", default=[])
    parser.add_argument("--owned-source-id", action="append", default=[])
    parser.add_argument("--tenant-id", default=None)
    return parser


def _target_policy_from_args(args: argparse.Namespace):
    base = target_policy_from_env()
    return build_target_policy_config(
        tenant_id=getattr(args, "tenant_id", None) or base.tenant_id,
        policy=getattr(args, "target_policy", None) or base.policy,
        owned_source_ids=[*base.owned_source_ids, *(getattr(args, "owned_source_id", None) or [])],
        allowed_source_urls=[*base.allowed_source_urls, *(getattr(args, "allow_source_url", None) or [])],
    )


def _plan_from_dict(data: dict) -> object:
    class PlanView:
        def __init__(self, payload):
            self.__dict__.update(payload)

    return PlanView(data)


def main() -> None:
    args = build_parser().parse_args()
    try:
        payload = asyncio.run(run_reply_batch(args))
    except BrowserCdpNotConfiguredError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    except ModuleNotFoundError as exc:
        if exc.name == "browser_use":
            raise SystemExit("ERROR: browser-use is not installed in this Python environment") from exc
        raise
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
