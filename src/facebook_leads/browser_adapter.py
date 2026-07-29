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


def require_browser_cdp(env: Mapping[str, str] | None = None, *, cdp_url: str | None = None) -> str:
    explicit = (cdp_url or "").strip()
    if explicit:
        return explicit
    source = env if env is not None else os.environ
    value = (source.get("FACEBOOK_CDP_URL") or source.get("BROWSER_CDP") or "").strip()
    if not value:
        raise BrowserCdpNotConfiguredError("FACEBOOK_CDP_URL or BROWSER_CDP is required")
    return value


def get_browser_window_size(env: Mapping[str, str] | None = None) -> tuple[int, int]:
    source = env if env is not None else os.environ
    return int(source.get("RESOLUTION_WIDTH", "1920")), int(source.get("RESOLUTION_HEIGHT", "1080"))


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
    pages = await list_context_pages(browser_context)
    open_pages = [candidate for candidate in pages if not _is_page_closed(candidate)]
    signed_in_candidates = [
        candidate
        for candidate in open_pages
        if _is_facebook_page_url(getattr(candidate, "url", "")) and not await _has_login_form(candidate)
    ]

    if page in signed_in_candidates:
        return page

    for candidate in signed_in_candidates:
        url = getattr(candidate, "url", "")
        if _is_facebook_content_page_url(url):
            return candidate
    for candidate in signed_in_candidates:
        return candidate

    if _is_facebook_page_url(getattr(page, "url", "")):
        return page

    for candidate in open_pages:
        url = getattr(candidate, "url", "")
        if _is_facebook_page_url(url):
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


async def _has_login_form(page: Any) -> bool:
    for selector in ("input[name='email']", "input[name='pass']", "form[action*='login']", "[data-testid='royal_login_button']"):
        try:
            if await page.locator(selector).count() > 0:
                return True
        except Exception:
            continue
    return False


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
