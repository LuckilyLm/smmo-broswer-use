from __future__ import annotations

import time


async def open_content(page, url: str, timeout_ms: int = 30000) -> dict:
    started = time.perf_counter()
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    ready = await wait_for_facebook_content_ready(page)
    return {
        "requested_url": url,
        "final_url": getattr(page, "url", None),
        "redirected": bool(getattr(page, "url", None) and getattr(page, "url", None) != url),
        "ready": ready,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


async def wait_for_facebook_content_ready(page, timeout_ms: int = 10000) -> dict:
    elapsed_ms = 0
    interval_ms = 500
    last_summary = {}
    while elapsed_ms <= timeout_ms:
        last_summary = await _content_ready_summary(page)
        if last_summary.get("body_present") and not last_summary.get("is_search_page") and (
            last_summary.get("has_reel_viewer")
            or last_summary.get("has_post_article")
            or last_summary.get("comment_button_count", 0) > 0
        ):
            return {"success": True, **last_summary}
        try:
            await page.wait_for_timeout(interval_ms)
        except Exception:
            break
        elapsed_ms += interval_ms
    return {"success": False, **last_summary}


async def _content_ready_summary(page) -> dict:
    if hasattr(page, "content_ready_summary"):
        return page.content_ready_summary
    script = """
    () => {
      const url = location.href;
      const bodyText = document.body ? (document.body.innerText || '') : '';
      const buttons = Array.from(document.querySelectorAll('[role="button"], button'));
      return {
        url,
        title: document.title,
        body_present: Boolean(document.body),
        is_search_page: /facebook\\.com\\/search\\//i.test(url),
        has_reel_viewer: /facebook\\.com\\/reel\\//i.test(url) && bodyText.length > 0,
        has_post_article: document.querySelectorAll('[role="article"]').length > 0,
        comment_button_count: buttons.filter((button) => /^(评论|comment|comments)/i.test(button.getAttribute('aria-label') || button.innerText || '')).length
      };
    }
    """
    try:
        return await page.evaluate(script)
    except Exception as exc:
        return {"error": str(exc)}
