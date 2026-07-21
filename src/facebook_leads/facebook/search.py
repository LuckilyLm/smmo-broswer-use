from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

from .models import FacebookContentCandidate, FacebookContentType

FACEBOOK_HOST_SUFFIXES = ("facebook.com", "fb.watch")
CONTENT_PATH_MARKERS = ("/posts/", "/reel/", "/reels/", "/videos/")
CONTENT_QUERY_KEYS = {"story_fbid", "v"}
SAFE_QUERY_KEYS = {"story_fbid", "fbid", "id", "v"}


@dataclass(frozen=True)
class AnchorRecord:
    href: str
    text: str | None = None
    aria_label: str | None = None


def build_facebook_search_url(keyword: str) -> str:
    encoded = quote_plus(keyword.strip())
    return f"https://www.facebook.com/search/top/?q={encoded}"


def normalize_facebook_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.netloc and parsed.path.startswith("/"):
        parsed = urlparse(f"https://www.facebook.com{url}")
    host = parsed.netloc.lower()
    if not _is_facebook_host(host):
        return None
    query = urlencode(
        [(key, value) for key, value in parse_qsl(parsed.query) if key in SAFE_QUERY_KEYS]
    )
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(("https", host, path, "", query, ""))


def classify_facebook_content_url(url: str) -> FacebookContentType:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query_keys = {key for key, _ in parse_qsl(parsed.query)}
    if "/reel/" in path or "/reels/" in path:
        return "reel"
    if "/videos/" in path or "v" in query_keys:
        return "video"
    if "/posts/" in path or "story_fbid" in query_keys or parsed.path.endswith("/permalink.php"):
        return "post"
    return "unknown"


def is_candidate_content_url(url: str) -> bool:
    normalized = normalize_facebook_url(url)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    path = parsed.path.lower()
    query_keys = {key for key, _ in parse_qsl(parsed.query)}
    return any(marker in path for marker in CONTENT_PATH_MARKERS) or bool(
        query_keys & CONTENT_QUERY_KEYS
    ) or path.endswith("/permalink.php") or (
        "fbid" in query_keys and path.endswith("/photo.php")
    )


async def search_facebook_contents(
    page,
    keyword: str,
    limit: int = 10,
    max_scrolls: int = 5,
) -> list[FacebookContentCandidate]:
    await page.goto(build_facebook_search_url(keyword), wait_until="domcontentloaded", timeout=30000)
    await _wait_for_candidate_anchors(page)
    candidates = await discover_content_candidates(
        page,
        limit=limit,
        max_scrolls=max_scrolls,
        discovered_from=getattr(page, "url", None),
    )
    return candidates[:limit]


async def discover_content_candidates(
    page,
    limit: int = 10,
    max_scrolls: int = 5,
    discovered_from: str | None = None,
) -> list[FacebookContentCandidate]:
    candidates: list[FacebookContentCandidate] = []
    seen: set[str] = set()
    for scroll_index in range(max(0, max_scrolls) + 1):
        for anchor_index, anchor in enumerate(await _extract_anchor_records(page)):
            if _is_search_noise_anchor(anchor):
                continue
            normalized = normalize_facebook_url(anchor.href)
            if not normalized or normalized in seen or not is_candidate_content_url(normalized):
                continue
            seen.add(normalized)
            candidates.append(
                FacebookContentCandidate(
                    url=normalized,
                    content_type=classify_facebook_content_url(normalized),
                    text_preview=_compact(anchor.text or anchor.aria_label),
                    author_name=None,
                    discovered_from=discovered_from,
                    discovery_index=anchor_index,
                )
            )
            if len(candidates) >= limit:
                return candidates

        if scroll_index >= max_scrolls:
            break
        await _scroll_once(page)

    return candidates


async def _wait_for_candidate_anchors(
    page,
    timeout_ms: int = 8000,
    interval_ms: int = 500,
) -> None:
    elapsed_ms = 0
    while elapsed_ms <= timeout_ms:
        anchors = await _extract_anchor_records(page)
        if any(
            is_candidate_content_url(normalized)
            for normalized in (normalize_facebook_url(anchor.href) for anchor in anchors)
            if normalized
        ):
            return
        try:
            await page.wait_for_timeout(interval_ms)
        except Exception:
            return
        elapsed_ms += interval_ms


async def _extract_anchor_records(page) -> list[AnchorRecord]:
    if hasattr(page, "anchor_records"):
        return [AnchorRecord(**record) for record in page.anchor_records]
    script = """
    () => Array.from(document.querySelectorAll('a[href]')).map((a) => ({
      href: a.href || a.getAttribute('href') || '',
      text: (a.innerText || a.textContent || '').slice(0, 500),
      aria_label: a.getAttribute('aria-label') || ''
    }))
    """
    try:
        raw_records = await page.evaluate(script)
    except Exception:
        raw_records = []
    records: list[AnchorRecord] = []
    for record in raw_records or []:
        if isinstance(record, dict):
            records.append(
                AnchorRecord(
                    href=str(record.get("href") or ""),
                    text=record.get("text"),
                    aria_label=record.get("aria_label"),
                )
            )
    return records


async def _scroll_once(page) -> None:
    if hasattr(page, "scroll_once"):
        await page.scroll_once()
        return
    try:
        await page.evaluate("() => window.scrollBy(0, Math.floor(window.innerHeight * 0.8))")
        await page.wait_for_timeout(1000)
    except Exception:
        try:
            await page.wait_for_timeout(300)
        except Exception:
            return


def _compact(text: str | None, limit: int = 240) -> str | None:
    if not text:
        return None
    compacted = " ".join(text.split())
    return compacted[:limit] if compacted else None


def _is_facebook_host(host: str) -> bool:
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in FACEBOOK_HOST_SUFFIXES)


def _is_search_noise_anchor(anchor: AnchorRecord) -> bool:
    parsed = urlparse(anchor.href or "")
    path = parsed.path.lower()
    if path.startswith("/login_alerts/"):
        return True
    text = _compact(" ".join(filter(None, [anchor.text, anchor.aria_label])), limit=500) or ""
    noise_markers = (
        "未读",
        "新登录",
        "登录情况",
        "赞了你的评论",
        "reacted to your comment",
        "new login",
        "login alert",
    )
    return any(marker.lower() in text.lower() for marker in noise_markers)
