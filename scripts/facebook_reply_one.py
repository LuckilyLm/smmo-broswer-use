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
    cdp_url = require_browser_cdp()

    from browser_use.browser.browser import BrowserConfig
    from browser_use.browser.context import BrowserContextConfig
    from src.browser.custom_browser import CustomBrowser

    browser = CustomBrowser(
        config=BrowserConfig(
            cdp_url=cdp_url,
            headless=False,
            keep_alive=True,
            new_context_config=BrowserContextConfig(keep_alive=True),
        )
    )
    browser_context = await browser.new_context(
        BrowserContextConfig(keep_alive=True, force_new_context=False)
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
    parser.add_argument("--artifacts-dir", default="artifacts/facebook_leads/replies")
    parser.add_argument("--history-path", default="artifacts/facebook_leads/reply_history.jsonl")
    return parser


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
    if result.get("error"):
        print(f"error={result['error']}")
    if payload.get("paths"):
        print(f"reply_result_json={payload['paths']['reply_result_json']}")


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
