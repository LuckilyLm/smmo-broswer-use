from __future__ import annotations

import re
from dataclasses import replace
from typing import Any
from urllib.parse import parse_qs, urlparse

from .models import FacebookContentCandidate, FacebookContentType
from .search import classify_facebook_content_url


UI_PREVIEW_TEXT = {
    "facebook",
    "reels",
    "reel",
    "like",
    "comment",
    "comments",
    "share",
    "follow",
    "following",
    "查看更多",
    "查看翻译",
    "查看所有者个人主页",
    "赞",
    "评论",
    "分享",
    "关注",
}


async def detect_content_type(
    url: str | None,
    page: Any | None = None,
    discovered_type: str | None = None,
    final_url: str | None = None,
) -> FacebookContentType:
    final_detected = detect_content_type_from_url(final_url)
    if final_detected != "unknown":
        return final_detected

    requested_detected = detect_content_type_from_url(url)
    if requested_detected != "unknown":
        return requested_detected

    if discovered_type and discovered_type != "unknown":
        return _valid_content_type(discovered_type)

    if page is not None:
        page_detected = await _detect_content_type_from_page(page)
        if page_detected != "unknown":
            return page_detected

    return "unknown"


def detect_content_type_from_url(url: str | None) -> FacebookContentType:
    if not url:
        return "unknown"
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parse_qs(parsed.query)

    if "/reel/" in path or "/reels/" in path:
        return "reel"
    if "/videos/" in path:
        return "video"
    if "/posts/" in path or path.endswith("/permalink.php"):
        return "post"
    if "story_fbid" in query:
        return "post"

    return _valid_content_type(classify_facebook_content_url(url))


async def extract_content_metadata(
    page: Any,
    discovered_candidate: FacebookContentCandidate,
) -> tuple[FacebookContentCandidate, dict[str, Any]]:
    requested_url = discovered_candidate.url
    final_url = getattr(page, "url", None) or requested_url
    content_type = await detect_content_type(
        requested_url,
        page=page,
        discovered_type=discovered_candidate.content_type,
        final_url=final_url,
    )

    extracted_preview = await extract_content_preview(page, content_type)
    candidate_preview = _clean_preview(discovered_candidate.text_preview)
    text_preview = extracted_preview or candidate_preview or fallback_content_preview(content_type)

    extracted_author = await extract_content_author(page)
    author_name = extracted_author or _clean_author(discovered_candidate.author_name)

    merged = replace(
        discovered_candidate,
        content_type=content_type,
        text_preview=text_preview,
        author_name=author_name,
    )
    return merged, {
        "requested_url": requested_url,
        "final_url": final_url,
        "content_type": content_type,
        "text_preview": text_preview,
        "author_name": author_name,
        "text_preview_source": "page" if extracted_preview else ("candidate" if candidate_preview else "fallback"),
        "author_source": "page" if extracted_author else ("candidate" if author_name else "missing"),
    }


async def extract_content_preview(page: Any, content_type: str | None) -> str | None:
    if hasattr(page, "content_preview"):
        return _clean_preview(getattr(page, "content_preview"))

    data = await _safe_evaluate(page, _CONTENT_PREVIEW_SCRIPT)
    if isinstance(data, dict):
        priority_values = [
            data.get("og_description"),
            data.get("meta_description"),
            data.get("og_title"),
            data.get("title"),
        ]
        visible_values = data.get("visible_texts")
        if isinstance(visible_values, list):
            priority_values.extend(visible_values)
        for value in priority_values:
            cleaned = _clean_preview(value, content_type)
            if cleaned:
                return cleaned

    return None


async def extract_content_author(page: Any, content_root: Any | None = None) -> str | None:
    if content_root is not None and hasattr(content_root, "content_author"):
        return _clean_author(getattr(content_root, "content_author"))
    if hasattr(page, "content_author"):
        return _clean_author(getattr(page, "content_author"))

    data = await _safe_evaluate(page, _CONTENT_AUTHOR_SCRIPT)
    if isinstance(data, dict):
        for value in data.get("authors") or []:
            cleaned = _clean_author(value)
            if cleaned:
                return cleaned
        for value in (data.get("og_title"), data.get("title")):
            cleaned = _author_from_title(value)
            if cleaned:
                return cleaned
    return None


def is_meaningful_content_preview(value: str | None, content_type: str | None = None) -> bool:
    compact = _compact(value)
    if not compact:
        return False
    normalized = compact.lower()
    if normalized in UI_PREVIEW_TEXT:
        return False
    if re.fullmatch(r"\(?\d+\)?\s*facebook", normalized):
        return False
    tokens = {token for token in re.split(r"[\s|·\-_/]+", normalized) if token}
    if tokens and tokens <= UI_PREVIEW_TEXT:
        return False
    if compact == fallback_content_preview(content_type):
        return True
    if re.fullmatch(r"\d+\s*(秒|分钟|小时|天|周|月|年)", compact):
        return False
    if re.fullmatch(r"\d+\s*(s|m|h|d|w|mo|y)", compact, re.I):
        return False
    if re.fullmatch(r"\d{1,2}月\d{1,2}日", compact):
        return False
    if normalized in {"today", "yesterday", "昨天", "今天"}:
        return False
    if len(compact) < 4 and not re.search(r"[\u4e00-\u9fff]", compact):
        return False
    return True


def fallback_content_preview(content_type: str | None) -> str:
    return {
        "reel": "Facebook 短视频",
        "post": "Facebook 帖子",
        "video": "Facebook 视频",
    }.get(content_type or "unknown", "Facebook 内容")


def _clean_preview(value: Any, content_type: str | None = None) -> str | None:
    compact = _compact(value)
    if not is_meaningful_content_preview(compact, content_type):
        return None
    return compact


def _clean_author(value: Any) -> str | None:
    compact = _compact(value)
    if not compact:
        return None
    if compact.lower() in UI_PREVIEW_TEXT:
        return None
    if re.search(r"查看(所有者|作者).{0,6}个人主页", compact):
        return None
    if re.fullmatch(r"(view|see)\s+(owner|author).{0,20}(profile|page)", compact, re.I):
        return None
    if re.fullmatch(r"\d+\s*(秒|分钟|小时|天|周|月|年|s|m|h|d|w|mo|y)", compact, re.I):
        return None
    return compact


def _author_from_title(value: Any) -> str | None:
    compact = _compact(value)
    if not compact:
        return None
    patterns = [
        r"^(.+?)\s+(?:on|在)\s+Facebook\b",
        r"^(.+?)\s+的(?:帖子|视频|短视频)",
        r"^(.+?)\s+-\s+Facebook\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact, re.I)
        if match:
            return _clean_author(match.group(1))
    return None


def _valid_content_type(value: str | None) -> FacebookContentType:
    if value in {"post", "reel", "video"}:
        return value
    return "unknown"


def _compact(value: Any) -> str | None:
    if value is None:
        return None
    compact = " ".join(str(value).split()).strip()
    return compact or None


async def _safe_evaluate(page: Any, script: str) -> Any:
    if not hasattr(page, "evaluate"):
        return None
    try:
        return await page.evaluate(script)
    except Exception:
        return None


_CONTENT_PREVIEW_SCRIPT = """
() => {
  const text = (node) => (node && (node.innerText || node.textContent || '') || '').trim();
  const attr = (selector, name) => document.querySelector(selector)?.getAttribute(name) || '';
  const selectors = [
    '[data-ad-preview="message"]',
    '[data-pagelet^="Reels"] [dir="auto"]',
    '[role="main"] h1',
    '[role="main"] h2',
    '[role="main"] [dir="auto"]'
  ];
  const visibleTexts = [];
  for (const selector of selectors) {
    for (const node of Array.from(document.querySelectorAll(selector)).slice(0, 20)) {
      const rect = node.getBoundingClientRect();
      const value = text(node);
      if (value && rect.width > 0 && rect.height > 0) visibleTexts.push(value);
    }
  }
  return {
    og_description: attr('meta[property="og:description"]', 'content'),
    meta_description: attr('meta[name="description"]', 'content'),
    og_title: attr('meta[property="og:title"]', 'content'),
    title: document.title || '',
    visible_texts: visibleTexts
  };
}
"""


_CONTENT_AUTHOR_SCRIPT = """
() => {
  const text = (node) => (node && (node.innerText || node.textContent || '') || '').trim();
  const attr = (selector, name) => document.querySelector(selector)?.getAttribute(name) || '';
  const badHref = /(\\/reel\\/|\\/reels\\/|\\/posts\\/|\\/videos\\/|\\/groups\\/|\\/watch|\\/search\\/|\\/login_alerts\\/|comment_id=)/i;
  const badText = /^(Facebook|Reels?|Like|Comment|Share|Follow|赞|评论|分享|关注|查看更多|查看翻译)$/i;
  const candidates = [];
  const roots = Array.from(document.querySelectorAll('[role="main"], [role="article"]')).slice(0, 3);
  for (const root of roots.length ? roots : [document.body]) {
    for (const link of Array.from(root.querySelectorAll('a[href]')).slice(0, 80)) {
      const href = link.getAttribute('href') || '';
      const value = text(link) || link.getAttribute('aria-label') || '';
      const rect = link.getBoundingClientRect();
      if (!value || badText.test(value) || badHref.test(href)) continue;
      if (rect.width <= 0 || rect.height <= 0 || rect.top > 900) continue;
      candidates.push(value);
    }
  }
  return {
    authors: candidates,
    og_title: attr('meta[property="og:title"]', 'content'),
    title: document.title || ''
  };
}
"""


async def _detect_content_type_from_page(page: Any) -> FacebookContentType:
    if hasattr(page, "content_type"):
        return _valid_content_type(getattr(page, "content_type"))
    data = await _safe_evaluate(
        page,
        """
        () => {
          const url = location.href;
          const body = document.body ? document.body.innerText || '' : '';
          return {
            url,
            has_reel: /facebook\\.com\\/reels?\\//i.test(url) || /\\bReels?\\b/.test(body),
            has_video: /facebook\\.com\\/.+\\/videos\\//i.test(url),
            has_article: document.querySelectorAll('[role="article"]').length > 0
          };
        }
        """,
    )
    if not isinstance(data, dict):
        return "unknown"
    if data.get("has_reel"):
        return "reel"
    if data.get("has_video"):
        return "video"
    if data.get("has_article"):
        return "post"
    return detect_content_type_from_url(data.get("url"))
