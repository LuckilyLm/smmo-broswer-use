from __future__ import annotations

import time


async def open_content(page, url: str, timeout_ms: int = 30000) -> dict:
    started = time.perf_counter()
    attempts = []
    for attempt in range(1, 3):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            attempts.append({"attempt": attempt, "status": "goto_success"})
            break
        except Exception as exc:
            readiness = await evaluate_page_readiness(page)
            attempts.append(
                {
                    "attempt": attempt,
                    "status": "goto_timeout_or_error",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "readiness": readiness,
                }
            )
            if readiness.get("status") in {"ready", "degraded"}:
                return await _open_success_payload(page, url, started, attempts, "navigation_degraded_success")
            if attempt >= 2:
                raise
            try:
                await page.wait_for_timeout(1000)
            except Exception:
                pass
    return await _open_success_payload(page, url, started, attempts, "navigation_success")


async def _open_success_payload(page, url: str, started: float, attempts: list[dict], navigation_status: str) -> dict:
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
        "navigation_status": navigation_status,
        "attempt_count": len(attempts),
        "attempts": attempts,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


async def evaluate_page_readiness(page) -> dict:
    summary = await _content_ready_summary(page)
    if summary.get("body_present") and not summary.get("is_search_page") and (
        summary.get("has_reel_viewer")
        or summary.get("has_post_article")
        or summary.get("comment_button_count", 0) > 0
    ):
        return {"status": "ready", **summary}
    if summary.get("body_present") and not summary.get("is_search_page") and (
        summary.get("title") or summary.get("url")
    ):
        return {"status": "degraded", **summary}
    return {"status": "not_ready", **summary}


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
