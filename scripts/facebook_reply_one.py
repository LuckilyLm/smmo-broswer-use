from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

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
from src.facebook_leads.facebook.reply import (  # noqa: E402
    ReplyRequest,
    load_reply_request_from_lead_report,
    reply_to_comment,
)


async def run_reply_one(args: argparse.Namespace) -> dict:
    request = build_reply_request(args)
    print_target_preview(request)
    if request.confirm_send and not request.yes and not request.send_confirmed:
        request = request_with_confirmation(request, confirm_interactive(args))
    if request.confirm_send and not request.yes and not request.send_confirmed:
        return await reply_to_comment(
            None,
            request,
            artifacts_dir=args.artifacts_dir,
            history_path=args.history_path,
        )
    if request.acceptance_test and not request.confirm_send and not request.preview_only:
        request = request_with_preview_only(request)
        return await reply_to_comment(
            None,
            request,
            artifacts_dir=args.artifacts_dir,
            history_path=args.history_path,
        )
    if request.preview_only and not request.acceptance_test:
        return await reply_to_comment(
            None,
            request,
            artifacts_dir=args.artifacts_dir,
            history_path=args.history_path,
        )
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
    page = await select_active_or_facebook_page(browser_context)
    return await reply_to_comment(
        page,
        request,
        artifacts_dir=args.artifacts_dir,
        history_path=args.history_path,
    )


def build_reply_request(args: argparse.Namespace) -> ReplyRequest:
    if args.lead_report:
        if args.lead_index is None:
            raise ValueError("--lead-index is required with --lead-report")
        return load_reply_request_from_lead_report(
            args.lead_report,
            args.lead_index,
            args.reply_text,
            use_suggested_reply=args.use_suggested_reply,
            confirm_send=args.confirm_send,
            yes=args.yes,
            keep_filled=args.keep_filled,
            allow_duplicate=args.allow_duplicate,
            send_confirmed=getattr(args, "send_confirmed", False),
            preview_only=getattr(args, "preview_only", False),
            verify_timeout_seconds=getattr(args, "verify_timeout_seconds", 15.0),
            acceptance_test=getattr(args, "acceptance_test", False),
        )
    if not args.source_content_url:
        raise ValueError("--source-content-url is required without --lead-report")
    if not args.reply_text:
        raise ValueError("--reply-text is required without --lead-report")
    return ReplyRequest(
        source_content_url=args.source_content_url,
        direct_comment_url=args.direct_comment_url,
        comment_id=args.comment_id,
        author_name=args.author_name,
        comment_text=args.comment_text,
        fingerprint=args.fingerprint,
        reply_text=args.reply_text,
        confirm_send=args.confirm_send,
        yes=args.yes,
        keep_filled=args.keep_filled,
        allow_duplicate=args.allow_duplicate,
        reply_source="manual",
        send_confirmed=getattr(args, "send_confirmed", False),
        preview_only=getattr(args, "preview_only", False),
        verify_timeout_seconds=getattr(args, "verify_timeout_seconds", 15.0),
        acceptance_test=getattr(args, "acceptance_test", False),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely reply to one Facebook lead comment. Default is DRY RUN: fill then clear, never send."
    )
    parser.add_argument("--lead-report", default=None, help="Path to lead_report.json.")
    parser.add_argument(
        "--lead-index",
        type=int,
        default=None,
        help="1-based index from the final recommended follow-up list in the HTML report.",
    )
    parser.add_argument("--source-content-url", default=None)
    parser.add_argument("--direct-comment-url", default=None)
    parser.add_argument("--comment-id", default=None)
    parser.add_argument("--author-name", default=None)
    parser.add_argument("--comment-text", default=None)
    parser.add_argument("--fingerprint", default=None)
    parser.add_argument("--reply-text", default=None)
    parser.add_argument("--use-suggested-reply", action="store_true", help="Use llm_review.suggested_reply from the selected lead.")
    parser.add_argument("--confirm-send", action="store_true", help="Request a real send. Requires --yes too.")
    parser.add_argument("--yes", action="store_true", help="Second protection gate for real send.")
    parser.add_argument("--keep-filled", action="store_true", help="Dry run leaves the typed text in the composer.")
    parser.add_argument("--allow-duplicate", action="store_true", help="Allow real send even if local history has this comment.")
    parser.add_argument("--preview-only", action="store_true", help="Print target lead and reply text without opening the reply input.")
    parser.add_argument("--acceptance-test", action="store_true", help="Print Phase 4D.1 acceptance summaries without bypassing send safety gates.")
    parser.add_argument("--verify-timeout-seconds", type=float, default=15.0)
    parser.add_argument("--artifacts-dir", default="artifacts/facebook_leads/replies")
    parser.add_argument("--history-path", default="artifacts/facebook_leads/reply_history.jsonl")
    return parser


def request_with_confirmation(request: ReplyRequest, confirmed: bool) -> ReplyRequest:
    return ReplyRequest(
        **{
            **request.to_dict(),
            "send_confirmed": confirmed,
        }
    )


def request_with_preview_only(request: ReplyRequest) -> ReplyRequest:
    return ReplyRequest(
        **{
            **request.to_dict(),
            "preview_only": True,
        }
    )


def confirm_interactive(args: argparse.Namespace) -> bool:
    if not sys.stdin or not sys.stdin.isatty():
        print("Interactive confirmation unavailable. Use --yes only after manual verification.")
        return False
    value = input("Type SEND to confirm: ").strip()
    return value == "SEND"


def print_target_preview(request: ReplyRequest) -> None:
    if request.acceptance_test:
        print("=== Phase 4D.1 Acceptance Test ===")
    print("Target Lead")
    print(f"Author: {request.author_name or 'unknown'}")
    print(f"Comment: {request.comment_text or ''}")
    print(f"Source: {request.source_content_url}")
    print(f"Direct comment: {request.direct_comment_url or ''}")
    print(f"reply_source={request.reply_source}")
    print("Final reply text:")
    print(request.reply_text)
    if request.acceptance_test and not request.confirm_send:
        print("Acceptance test prepared but no real send confirmation provided.")
        print("NO REAL SEND WAS ATTEMPTED")


def print_summary(payload: dict) -> None:
    result = payload["result"]
    mode = "SEND MODE" if not result["dry_run"] else "DRY RUN"
    print(mode)
    if result["dry_run"]:
        print("未发送")
    print(f"located={result['located']}")
    print(f"locate_strategy={result['locate_strategy']}")
    print(f"matched_count={result['matched_count']}")
    print(f"reply_clicked={result['reply_clicked']}")
    print(f"input_found={result['input_found']}")
    print(f"text_filled={result['text_filled']}")
    print(f"sent={result['sent']}")
    print(f"status={result.get('status')}")
    print(f"verified={result.get('verified')}")
    print(f"send_action_performed={result.get('send_action_performed')}")
    if result.get("error"):
        print(f"error={result['error']}")
    if payload.get("paths"):
        print(f"reply_result_json={payload['paths']['reply_result_json']}")
    if payload["request"].get("acceptance_test"):
        print("=== Acceptance Result ===")
        print(f"status:\n{result.get('status')}")
        print(f"send_action_performed:\n{result.get('send_action_performed')}")
        print(f"verified:\n{result.get('verified')}")
        print(f"sent:\n{result.get('sent')}")
        print(f"verification_strategy:\n{result.get('verification_strategy')}")
        print(f"verification_elapsed_ms:\n{result.get('verification_elapsed_ms')}")
        if payload.get("paths"):
            print(f"reply_result:\n{payload['paths']['reply_result_json']}")
        print(f"reply_history:\n{payload['request'].get('history_path', 'artifacts/facebook_leads/reply_history.jsonl')}")
        if result.get("status") == "unverified":
            print("SEND ACTION MAY HAVE OCCURRED.")
            print("DO NOT RETRY AUTOMATICALLY.")
            print("CHECK FACEBOOK MANUALLY FIRST.")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload = asyncio.run(run_reply_one(args))
    except BrowserCdpNotConfiguredError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    except ModuleNotFoundError as exc:
        if exc.name == "browser_use":
            raise SystemExit("ERROR: browser-use is not installed in this Python environment") from exc
        raise
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print_summary(payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
