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

from src.facebook_leads.browser_adapter import (  # noqa: E402
    BrowserCdpNotConfiguredError,
    require_browser_cdp,
    select_active_or_facebook_page,
)
from src.facebook_leads.facebook.diagnostics import (  # noqa: E402
    create_diagnostic_dir,
    save_failure_screenshot,
    write_json,
)
from src.facebook_leads.facebook.scanner import run_readonly_scan  # noqa: E402


async def run_cli_scan(args: argparse.Namespace) -> dict:
    total_started = time.perf_counter()
    cdp_url = require_browser_cdp()

    from browser_use.browser.browser import BrowserConfig
    from browser_use.browser.context import BrowserContextConfig
    from src.browser.custom_browser import CustomBrowser

    browser_started = time.perf_counter()
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
    browser_init_ms = _elapsed_ms(browser_started)

    page_started = time.perf_counter()
    page = await select_active_or_facebook_page(browser_context)
    get_page_ms = _elapsed_ms(page_started)

    result = await run_readonly_scan(
        page,
        keyword=args.keyword,
        content_limit=args.content_limit,
        comment_limit=args.comment_limit,
        max_scrolls=args.max_scrolls,
        max_expand_clicks=args.max_expand_clicks,
        current_page_only=args.current_page_only,
    )
    payload = result.to_dict()
    payload["timing"]["browser_init_ms"] = browser_init_ms
    payload["timing"]["get_page_ms"] = get_page_ms
    payload["timing"]["total_ms"] = _elapsed_ms(total_started)
    payload["diagnostics"]["closed_remote_chromium"] = False
    payload["diagnostics"]["close_called"] = False

    artifact_dir = create_diagnostic_dir(args.artifacts_dir)
    result_path = artifact_dir / "result.json"
    diagnostic_path = artifact_dir / "diagnostic.json"
    payload["diagnostics"]["artifact_dir"] = str(artifact_dir)
    payload["diagnostics"]["result_path"] = str(result_path)
    if not result.success:
        screenshot_path = await save_failure_screenshot(page, artifact_dir)
        if screenshot_path:
            payload["diagnostics"]["failure_screenshot"] = screenshot_path
    write_json(result_path, payload)
    write_json(diagnostic_path, payload["diagnostics"])
    if args.output:
        write_json(args.output, payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Facebook scanner. It may save failure screenshots under "
            "artifacts/facebook_leads; screenshots can contain account-visible page data."
        )
    )
    parser.add_argument("--keyword", default=None)
    parser.add_argument("--content-limit", type=int, default=5)
    parser.add_argument("--comment-limit", type=int, default=100)
    parser.add_argument("--max-scrolls", type=int, default=5)
    parser.add_argument("--max-expand-clicks", type=int, default=20)
    parser.add_argument("--output", default=None)
    parser.add_argument("--artifacts-dir", default="artifacts/facebook_leads")
    parser.add_argument(
        "--current-page-only",
        action="store_true",
        help="Scan the currently open Facebook content page without running search.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        payload = asyncio.run(run_cli_scan(args))
    except BrowserCdpNotConfiguredError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    except ModuleNotFoundError as exc:
        if exc.name == "browser_use":
            raise SystemExit(
                "ERROR: browser-use is not installed in this Python environment"
            ) from exc
        raise
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


if __name__ == "__main__":
    main()
