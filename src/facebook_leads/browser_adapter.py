from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse


class BrowserCdpNotConfiguredError(RuntimeError):
    """Raised when the integration spike has no existing CDP endpoint to use."""


class BrowserUsePageAccessorError(RuntimeError):
    """Raised when browser-use does not expose a usable current page accessor."""


@dataclass(frozen=True)
class PageSummary:
    index: int
    url: str
    is_closed: bool


def require_browser_cdp(env: Mapping[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    value = (source.get("BROWSER_CDP") or "").strip()
    if not value:
        raise BrowserCdpNotConfiguredError("BROWSER_CDP is required")
    return value


async def get_active_page(browser_context: Any) -> Any:
    """Return the browser-use 0.1.48 agent current Playwright Page."""

    if hasattr(browser_context, "get_agent_current_page"):
        return await browser_context.get_agent_current_page()
    if hasattr(browser_context, "get_current_page"):
        return await browser_context.get_current_page()
    raise BrowserUsePageAccessorError(
        "browser-use BrowserContext exposes neither get_agent_current_page() "
        "nor get_current_page()"
    )


async def select_active_or_facebook_page(browser_context: Any) -> Any:
    page = await get_active_page(browser_context)
    if _is_facebook_page_url(getattr(page, "url", "")):
        return page

    for candidate in await list_context_pages(browser_context):
        url = getattr(candidate, "url", "")
        if _is_facebook_content_page_url(url) and not _is_page_closed(candidate):
            return candidate
    for candidate in await list_context_pages(browser_context):
        url = getattr(candidate, "url", "")
        if _is_facebook_page_url(url) and not _is_page_closed(candidate):
            return candidate
    return page


async def list_context_pages(browser_context: Any) -> list[Any]:
    session = await browser_context.get_session()
    return list(session.context.pages)


async def summarize_pages(browser_context: Any) -> list[PageSummary]:
    summaries: list[PageSummary] = []
    for index, page in enumerate(await list_context_pages(browser_context)):
        is_closed = _is_page_closed(page)
        summaries.append(PageSummary(index=index, url=getattr(page, "url", ""), is_closed=is_closed))
    return summaries


async def verify_page_primitives(page: Any, goto_url: str | None = None) -> dict[str, Any]:
    before_url = getattr(page, "url", "")
    before_title = await page.title()
    body_count = await page.locator("body").count()
    result: dict[str, Any] = {
        "url_before": before_url,
        "title_before": before_title,
        "body_count_before": body_count,
    }
    if goto_url:
        await page.goto(goto_url)
        result.update(
            url_after=getattr(page, "url", ""),
            title_after=await page.title(),
            body_count_after=await page.locator("body").count(),
        )
    return result


def _is_page_closed(page: Any) -> bool:
    return bool(page.is_closed()) if hasattr(page, "is_closed") else False


def _is_facebook_page_url(url: str) -> bool:
    host = urlparse(url or "").netloc.lower()
    return host == "facebook.com" or host.endswith(".facebook.com")


def _is_facebook_content_page_url(url: str) -> bool:
    parsed = urlparse(url or "")
    path = parsed.path.lower()
    return _is_facebook_page_url(url) and (
        "/posts/" in path
        or "/reel/" in path
        or "/reels/" in path
        or "/videos/" in path
        or path.endswith("/permalink.php")
        or "story_fbid=" in parsed.query
    )
