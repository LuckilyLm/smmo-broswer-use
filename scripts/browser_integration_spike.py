from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.facebook_leads.browser_adapter import (
    BrowserCdpNotConfiguredError,
    get_active_page,
    require_browser_cdp,
    summarize_pages,
    verify_page_primitives,
)


async def run_spike(goto_url: str | None = None) -> dict:
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

    page = await get_active_page(browser_context)
    pages = await summarize_pages(browser_context)
    primitives = await verify_page_primitives(page, goto_url=goto_url)
    playwright_browser = await browser.get_playwright_browser()

    return {
        "cdp_url_configured": bool(cdp_url),
        "connected_contexts": len(playwright_browser.contexts),
        "page_count": len(pages),
        "pages": [page_summary.__dict__ for page_summary in pages],
        "active_page_url": page.url,
        "active_page_title": await page.title(),
        "primitive_results": primitives,
        "lifecycle": {
            "browser_keep_alive": browser.config.keep_alive,
            "context_keep_alive": browser_context.config.keep_alive,
            "closed_remote_chromium": False,
            "close_called": False,
        },
        "page_accessor_path": "BrowserContext.get_agent_current_page()",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Manual browser-use 0.1.48 CDP integration spike."
    )
    parser.add_argument(
        "--goto-example",
        action="store_true",
        help="Also run page.goto('https://example.com'). Do not use this on sensitive tabs.",
    )
    args = parser.parse_args()
    goto_url = "https://example.com" if args.goto_example else None
    try:
        result = asyncio.run(run_spike(goto_url=goto_url))
    except BrowserCdpNotConfiguredError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    except ModuleNotFoundError as exc:
        if exc.name == "browser_use":
            raise SystemExit(
                "ERROR: browser-use is not installed in this Python environment"
            ) from exc
        raise
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
