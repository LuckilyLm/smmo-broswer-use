from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from .comment_links import extract_comment_id_from_url, resolve_comment_links
from .models import FacebookComment

MORE_COMMENT_PATTERNS = (
    "view more comments",
    "see more comments",
    "more comments",
    "view previous comments",
    "查看更多评论",
    "更多评论",
    "查看之前的评论",
)
COMMENT_PANEL_PATTERNS = (
    "comment",
    "comments",
    "评论",
)
UI_ONLY_TEXT = {
    "like",
    "reply",
    "share",
    "comment",
    "send",
    "赞",
    "回复",
    "分享",
    "评论",
    "发送",
}


@dataclass(frozen=True)
class CommentRecord:
    comment_id: str | None = None
    author_name: str | None = None
    author_url: str | None = None
    author_extract_strategy: str | None = None
    text: str | None = None
    timestamp_text: str | None = None
    comment_url: str | None = None
    direct_comment_url: str | None = None
    comment_id_source: str | None = None
    is_reply: bool = False
    parent_comment_id: str | None = None


@dataclass(frozen=True)
class CommentRoot:
    root: Any
    root_type: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class CommentNodeLocation:
    locator: Any | None
    diagnostics: dict[str, Any]


@dataclass(frozen=True)
class CommentAuthor:
    author_name: str | None
    author_url: str | None
    strategy: str


async def expand_comments(page, max_expand_clicks: int = 20) -> dict[str, Any]:
    clicks = 0
    errors = 0
    scroll_diag: dict[str, Any] = {"rounds": []}
    unchanged_rounds = 0
    root_info = await find_comment_root(page)
    previous_count = await count_comment_candidates(root_info.root)
    panel_diag = await open_comment_panel(page, root_info)
    if panel_diag["opened"]:
        root_info = await find_comment_root(page)
        previous_count = await wait_for_comments_loaded(page, timeout_ms=15000, min_count=1)
        root_info = await find_comment_root(page)

    while clicks < max_expand_clicks and unchanged_rounds < 3:
        button = await _find_more_comments_button(page)
        if button is None:
            break
        try:
            await button.click(timeout=3000)
            clicks += 1
        except Exception:
            errors += 1
            unchanged_rounds += 1
            continue
        current_count = await _wait_for_comment_count_change(page, previous_count)
        if current_count <= previous_count:
            unchanged_rounds += 1
        else:
            unchanged_rounds = 0
        previous_count = current_count

    if previous_count > 0:
        root_info = await find_comment_root(page)
        scroll_diag = await scroll_comment_container(page, root_info, max_rounds=5)
        root_info = await find_comment_root(page)
        previous_count = await count_comment_candidates(root_info.root)

    return {
        "comment_panel": panel_diag,
        "opened_comment_panel": panel_diag["opened"],
        "comment_root_type": root_info.root_type,
        "comment_root": root_info.metadata,
        "expanded_comment_clicks": clicks,
        "expand_errors": errors,
        "final_comment_dom_count": previous_count,
        "comment_candidate_count_after_scroll": previous_count,
        "comment_scroll": scroll_diag,
        "stopped_after_unchanged_rounds": unchanged_rounds >= 3,
    }


async def extract_comments(
    page,
    source_content_url: str,
    root=None,
    limit: int = 200,
) -> list[FacebookComment]:
    if root is None:
        root = (await find_comment_root(page)).root
    records = await _extract_comment_records(root)
    comments: list[FacebookComment] = []
    seen: set[str] = set()
    for record in records:
        raw_text = _clean_text(record.text)
        timestamp = _clean_text(record.timestamp_text)
        author_info = extract_comment_author(record, raw_text)
        author = author_info.author_name
        text = _clean_comment_body_text(raw_text, author, timestamp)
        if not author and not text:
            continue
        if text and text.lower() in UI_ONLY_TEXT:
            continue
        if text and _is_non_comment_ui_text(text):
            continue
        link_resolution = resolve_comment_links(
            source_content_url=source_content_url,
            node_comment_id=record.comment_id,
            comment_url=record.comment_url,
            author_url=record.author_url,
            direct_comment_url=record.direct_comment_url,
            comment_id_source=record.comment_id_source,
        )
        fingerprint = make_comment_fingerprint(source_content_url, author, text, timestamp)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        comments.append(
            FacebookComment(
                comment_id=link_resolution.comment_id,
                author_name=author,
                author_url=record.author_url,
                text=text,
                timestamp_text=timestamp,
                comment_url=link_resolution.comment_url,
                is_reply=record.is_reply,
                parent_comment_id=record.parent_comment_id,
                source_content_url=source_content_url,
                fingerprint=fingerprint,
                direct_comment_url=link_resolution.direct_comment_url,
                comment_id_source=link_resolution.comment_id_source,
                author_extract_strategy=author_info.strategy,
            )
        )
        if len(comments) >= limit:
            break
    return comments


async def find_comment_root(page) -> CommentRoot:
    if hasattr(page, "comment_root"):
        return CommentRoot(page.comment_root, getattr(page.comment_root, "root_type", "page"), {})
    if hasattr(page, "roots"):
        roots = list(page.roots)
        scored = sorted(roots, key=lambda item: (getattr(item, "candidate_count", 0), _root_type_score(getattr(item, "root_type", ""))), reverse=True)
        if scored:
            root = scored[0]
            return CommentRoot(root, getattr(root, "root_type", "page"), {"candidate_count": getattr(root, "candidate_count", 0)})

    summary = await _comment_root_summary(page)
    if summary.get("best_selector"):
        try:
            return CommentRoot(
                page.locator(summary["best_selector"]).first,
                summary.get("root_type") or "page",
                summary,
            )
        except Exception:
            pass
    return CommentRoot(page, summary.get("root_type") or "page", summary)


async def count_comment_candidates(root) -> int:
    if hasattr(root, "candidate_count"):
        return int(root.candidate_count)
    if hasattr(root, "comment_records"):
        return len(root.comment_records)
    try:
        return int(await root.locator(_comment_candidate_selector()).count())
    except Exception:
        pass
    try:
        return int(await root.evaluate(_count_comment_candidates_script()))
    except Exception:
        return 0


async def open_comment_panel(page, root_info: CommentRoot | None = None) -> dict[str, Any]:
    import time

    started = time.perf_counter()
    before_root = root_info or await find_comment_root(page)
    before_count = await count_comment_candidates(before_root.root)
    result: dict[str, Any] = {
        "attempted": before_count == 0,
        "opened": False,
        "before": {"count": before_count, "root_type": before_root.root_type},
        "after": {},
        "root_type": before_root.root_type,
        "elapsed_ms": 0,
    }
    if before_count > 0:
        result["after"] = result["before"]
        return result
    if hasattr(page, "open_comments_panel"):
        result["opened"] = bool(await page.open_comments_panel())
    else:
        result["opened"] = await _click_comment_panel_button(page)
    after_root = await find_comment_root(page)
    after_count = await count_comment_candidates(after_root.root)
    result["after"] = {"count": after_count, "root_type": after_root.root_type}
    result["root_type"] = after_root.root_type
    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    return result


async def wait_for_comments_loaded(
    page,
    timeout_ms: int = 15000,
    min_count: int = 1,
) -> int:
    elapsed_ms = 0
    interval_ms = 500
    while elapsed_ms <= timeout_ms:
        root_info = await find_comment_root(page)
        count = await count_comment_candidates(root_info.root)
        if count >= min_count:
            return count
        try:
            await page.wait_for_timeout(interval_ms)
        except Exception:
            return count
        elapsed_ms += interval_ms
    root_info = await find_comment_root(page)
    return await count_comment_candidates(root_info.root)


async def scroll_comment_container(
    page,
    root_info: CommentRoot | None = None,
    max_rounds: int = 5,
) -> dict[str, Any]:
    rounds: list[dict[str, Any]] = []
    unchanged = 0
    root_info = root_info or await find_comment_root(page)
    for index in range(max(0, max_rounds)):
        before_count = await count_comment_candidates(root_info.root)
        metrics = await _scroll_comment_container_once(root_info.root)
        try:
            await page.wait_for_timeout(500)
        except Exception:
            pass
        root_info = await find_comment_root(page)
        after_count = await count_comment_candidates(root_info.root)
        entry = {
            "round": index + 1,
            "before_count": before_count,
            "after_count": after_count,
            **metrics,
        }
        rounds.append(entry)
        if after_count <= before_count:
            unchanged += 1
        else:
            unchanged = 0
        if unchanged >= 2:
            break
    return {"rounds": rounds, "stopped_after_unchanged_rounds": unchanged >= 2}


def make_comment_fingerprint(
    source_content_url: str,
    author_name: str | None,
    text: str | None,
    timestamp_text: str | None,
) -> str:
    raw = "\n".join(
        [
            source_content_url.strip(),
            (author_name or "").strip(),
            (text or "").strip(),
            (timestamp_text or "").strip(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_comment_author(record: CommentRecord, raw_text: str | None = None) -> CommentAuthor:
    author_name = _clean_text(record.author_name)
    author_url = _clean_text(record.author_url)
    if author_name:
        return CommentAuthor(
            author_name=author_name,
            author_url=author_url,
            strategy=record.author_extract_strategy or "profile_anchor",
        )

    fallback = _author_from_raw_text(raw_text)
    if fallback:
        return CommentAuthor(author_name=fallback, author_url=author_url, strategy="raw_text_first_line")

    return CommentAuthor(author_name=None, author_url=author_url, strategy="none")


async def locate_comment_node(
    page,
    comment_id: str | None = None,
    direct_comment_url: str | None = None,
    author_name: str | None = None,
    comment_text: str | None = None,
) -> CommentNodeLocation:
    comment_id = comment_id or extract_comment_id_from_url(direct_comment_url)
    if hasattr(page, "locate_comment_node"):
        return await page.locate_comment_node(
            comment_id=comment_id,
            direct_comment_url=direct_comment_url,
            author_name=author_name,
            comment_text=comment_text,
        )

    if comment_id:
        escaped_id = _css_attr_value(comment_id)
        nearest_count = await _comment_id_nearest_article_count(page, comment_id)
        if nearest_count == 1:
            locator = (
                page.locator(f"a[href*={escaped_id}]")
                .first
                .locator("xpath=ancestor::*[@role='article'][1]")
            )
            return _location(locator, "comment_id", nearest_count)
        if nearest_count > 1 and comment_text:
            refined_count = await _comment_id_nearest_article_count(page, comment_id, comment_text)
            if refined_count > 0:
                locator = (
                    page.locator("[role='article']")
                    .filter(has=page.locator(f"a[href*={escaped_id}]"))
                    .filter(has_text=_text_excerpt(comment_text))
                )
                return _location(locator, "comment_id_text", refined_count)

        selector = (
            f"[role='article'][data-commentid={escaped_id}], "
            f"[role='article'][id={escaped_id}], "
            f"[role='article']:has(a[href*={escaped_id}])"
        )
        locator = page.locator(selector)
        count = await _safe_locator_count(locator)
        if count == 1:
            return _location(locator, "comment_id", count)
        if count > 1 and comment_text:
            refined_locator = locator.filter(has_text=_text_excerpt(comment_text))
            refined_count = await _safe_locator_count(refined_locator)
            if refined_count == 1:
                return _location(refined_locator, "comment_id_text", refined_count)
            if refined_count > 0:
                return _location(refined_locator, "comment_id_text", refined_count)
            return _location(locator, "comment_id", count)
        if count > 1:
            return _location(locator, "comment_id", count)

    if author_name and comment_text:
        excerpt = _text_excerpt(comment_text)
        locator = page.locator("[role='article']").filter(has_text=author_name).filter(has_text=excerpt)
        count = await _safe_locator_count(locator)
        if count > 0:
            return _location(locator, "author_text", count)

    return CommentNodeLocation(
        locator=None,
        diagnostics={
            "found": False,
            "strategy": "none",
            "matched_count": 0,
            "ambiguous": False,
        },
    )


async def _extract_comment_records(page) -> list[CommentRecord]:
    if hasattr(page, "comment_records"):
        return [CommentRecord(**record) for record in page.comment_records]
    script = """
    () => {
      const articleNodes = Array.from(document.querySelectorAll('[role="article"], [aria-label*="comment" i]'));
      const isCommentHref = (href) => /comment_id=|reply_comment_id=|story_fbid=|permalink\\.php/i.test(href || '');
      const isFacebookHref = (href) => {
        try {
          const url = new URL(href, window.location.href);
          return url.hostname === 'facebook.com' || url.hostname.endsWith('.facebook.com');
        } catch {
          return false;
        }
      };
      const isProfileHref = (href) => {
        if (!isFacebookHref(href)) return false;
        try {
          const url = new URL(href, window.location.href);
          const path = url.pathname.replace(/\\/$/, '');
          if (path === '/profile.php') return Boolean(url.searchParams.get('id'));
          if (/\\/posts\\/|\\/videos\\/|\\/reel\\/|\\/reels\\/|\\/permalink\\.php|\\/photo/i.test(path)) return false;
          const segments = path.split('/').filter(Boolean);
          return segments.length === 1 && !['watch', 'groups', 'pages', 'events', 'marketplace', 'search'].includes(segments[0].toLowerCase());
        } catch {
          return false;
        }
      };
      const linkText = (link) => (link.innerText || link.textContent || '').trim();
      const looksLikeAuthorText = (text) => text.length > 1 && text.length <= 80 && !/^(Like|Reply|Share|Comment|Send|赞|回复|分享|评论|发送)$/i.test(text);
      const looksLikeTimeLink = (link) => {
        const text = linkText(link);
        return /^(\\d+\\s*(s|m|h|d|w|mo|y|秒|分钟|小时|天|周|月|年)|昨天|今天|yesterday|today)$/i.test(text);
      };
      return articleNodes.slice(0, 400).map((node) => {
        const links = Array.from(node.querySelectorAll('a[href]'));
        const authorLink = links.find((a) => looksLikeAuthorText(linkText(a)) && isProfileHref(a.href));
        const commentLinks = links.filter((a) => isCommentHref(a.href));
        const permalink = commentLinks.find((a) => looksLikeTimeLink(a))
          || commentLinks.find((a) => a !== authorLink)
          || commentLinks[0]
          || null;
        const text = (node.innerText || node.textContent || '').split('\\n')
          .map((part) => part.trim())
          .filter(Boolean)
          .filter((part) => !/^(Like|Reply|Share|Comment|Send|赞|回复|分享|评论|发送)$/i.test(part))
          .join('\\n')
          .slice(0, 3000);
        return {
          comment_id: node.getAttribute('data-commentid') || node.id || null,
          author_name: authorLink ? (authorLink.innerText || '').trim() : null,
          author_url: authorLink ? authorLink.href : null,
          author_extract_strategy: authorLink ? 'profile_anchor' : null,
          text,
          timestamp_text: null,
          comment_url: permalink ? permalink.href : null,
          direct_comment_url: null,
          comment_id_source: permalink ? 'comment_link' : 'unknown',
          is_reply: Boolean(node.closest('[aria-label*="reply" i]')),
          parent_comment_id: null
        };
      });
    }
    """
    try:
        raw_records = await page.evaluate(script)
    except Exception:
        raw_records = []
    records: list[CommentRecord] = []
    for record in raw_records or []:
        if isinstance(record, dict):
            records.append(CommentRecord(**{key: record.get(key) for key in CommentRecord.__dataclass_fields__}))
    return records


async def _find_more_comments_button(page):
    if hasattr(page, "next_more_comments_button"):
        return await page.next_more_comments_button()
    pattern = re.compile("|".join(re.escape(item) for item in MORE_COMMENT_PATTERNS), re.I)
    try:
        locator = page.get_by_role("button", name=pattern)
        if await locator.count() > 0:
            return locator.first
    except Exception:
        return None
    return None


async def _click_comment_panel_button(page) -> bool:
    pattern = re.compile(rf"^({'|'.join(re.escape(item) for item in COMMENT_PANEL_PATTERNS)})(?!.*(reply|send|回复|发送|发布))", re.I)
    try:
        locator = page.get_by_role("button", name=pattern)
        if await locator.count() == 0:
            return False
        await locator.first.click(timeout=3000)
        try:
            await page.wait_for_timeout(500)
        except Exception:
            pass
        return True
    except Exception:
        return False


async def _comment_dom_count(page) -> int:
    return await count_comment_candidates((await find_comment_root(page)).root)


async def _wait_for_comment_count_change(page, previous_count: int) -> int:
    for _ in range(5):
        try:
            await page.wait_for_timeout(200)
        except Exception:
            pass
        current_count = await _comment_dom_count(page)
        if current_count != previous_count:
            return current_count
    return await _comment_dom_count(page)


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = "\n".join(" ".join(line.split()) for line in value.splitlines())
    cleaned = cleaned.strip()
    return cleaned or None


def _clean_comment_body_text(
    raw_text: str | None,
    author_name: str | None,
    timestamp_text: str | None,
) -> str | None:
    if not raw_text:
        return None
    cleaned: list[str] = []
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if author_name and line == author_name.strip():
            continue
        if timestamp_text and line == timestamp_text.strip():
            continue
        if _is_comment_text_noise_line(line):
            continue
        cleaned.append(line)
    return "\n".join(cleaned) if cleaned else None


def _author_from_raw_text(raw_text: str | None) -> str | None:
    if not raw_text:
        return None
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    candidate = lines[0]
    body = next((line for line in lines[1:] if not _is_comment_text_noise_line(line)), None)
    if not body:
        return None
    if not _looks_like_author_name(candidate):
        return None
    return candidate


def _looks_like_author_name(value: str) -> bool:
    if not value:
        return False
    compact = " ".join(value.split())
    lowered = compact.lower()
    if len(compact) < 2 or len(compact) > 80:
        return False
    if _is_comment_text_noise_line(compact):
        return False
    if lowered in UI_ONLY_TEXT:
        return False
    if "?" in compact or "!" in compact or "." in compact:
        return False
    if re.search(r"\b(how much|price|pm|deliver|delivery|location|where|buy|need|want|interested)\b", lowered):
        return False
    if re.search(r"\d", compact):
        return False
    words = compact.split()
    if len(words) > 5:
        return False
    return any(char.isalpha() for char in compact)


def _is_comment_text_noise_line(line: str) -> bool:
    normalized = line.strip().lower()
    if normalized in UI_ONLY_TEXT:
        return True
    exact_noise = {
        "·",
        "作者",
        "author",
        "查看翻译",
        "see translation",
        "已编辑",
        "edited",
    }
    if normalized in exact_noise:
        return True
    if re.fullmatch(r"\d+", normalized):
        return True
    if re.fullmatch(r"\d+\s*(秒|分钟|小时|天|周|月|年)", normalized):
        return True
    if re.fullmatch(r"\d+\s*(s|m|h|d|w|mo|y)", normalized, re.I):
        return True
    return False


def _is_non_comment_ui_text(text: str) -> bool:
    lowered = text.lower()
    noisy = (
        "以 sz tom 的身份评论",
        "most relevant",
        "all comments",
        "最相关",
        "所有评论",
        "查看更多评论",
        "还没有任何评论",
        "抢沙发",
    )
    return any(item in lowered for item in noisy)


def _comment_candidate_selector() -> str:
    return "[role='article'], a[href*='comment_id'], a[href*='reply_comment_id']"


def _root_type_score(root_type: str) -> int:
    return {"nested_scroll_container": 4, "dialog": 3, "overlay": 2, "page": 1}.get(root_type, 0)


async def _comment_root_summary(page) -> dict[str, Any]:
    script = """
    () => {
      const candidateSelector = "[role='article'], a[href*='comment_id'], a[href*='reply_comment_id']";
      const visible = (el) => {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
      };
      const textOf = (el) => (el.innerText || el.textContent || '').trim();
      const candidates = [];
      const push = (selector, type, el) => {
        if (!el || !visible(el)) return;
        const count = el.querySelectorAll(candidateSelector).length;
        const commentHints = el.querySelectorAll('[aria-label*="comment" i], [aria-label*="评论" i]').length;
        const scrollables = Array.from(el.querySelectorAll('*')).filter((node) => node.scrollHeight > node.clientHeight + 20).length;
        const text = textOf(el).slice(0, 500);
        candidates.push({selector, type, count, commentHints, scrollables, textLength: text.length, noComments: /还没有任何评论|no comments/i.test(text)});
      };
      Array.from(document.querySelectorAll('[role="dialog"]')).forEach((el, index) => push(`[role="dialog"] >> nth=${index}`, 'dialog', el));
      Array.from(document.querySelectorAll('[aria-modal="true"]')).forEach((el, index) => push(`[aria-modal="true"] >> nth=${index}`, 'overlay', el));
      push('body', 'page', document.body);
      candidates.sort((a, b) => {
        if (b.count !== a.count) return b.count - a.count;
        if (b.commentHints !== a.commentHints) return b.commentHints - a.commentHints;
        return b.scrollables - a.scrollables;
      });
      const best = candidates[0] || {selector: 'body', type: 'page', count: 0, commentHints: 0, scrollables: 0};
      return {
        root_type: best.type || 'page',
        best_selector: best.selector === 'body' ? null : best.selector,
        candidate_count: best.count || 0,
        dialog_count: document.querySelectorAll('[role="dialog"]').length,
        aria_modal_count: document.querySelectorAll('[aria-modal="true"]').length,
        visible_text_container_count: Array.from(document.querySelectorAll('div, span')).filter((el) => visible(el) && textOf(el).length > 0).length,
        candidates: candidates.slice(0, 8)
      };
    }
    """
    try:
        return await page.evaluate(script)
    except Exception as exc:
        return {"root_type": "page", "error": str(exc)}


def _count_comment_candidates_script() -> str:
    return f"(root) => (root || document.body).querySelectorAll({ _js_string(_comment_candidate_selector()) }).length"


async def _scroll_comment_container_once(root) -> dict[str, Any]:
    if hasattr(root, "scroll_comment_container_once"):
        return await root.scroll_comment_container_once()
    script = """
    (root) => {
      const rootEl = (!root || root === document) ? document.body : root;
      const candidates = Array.from(rootEl.querySelectorAll('*'))
        .filter((el) => el.scrollHeight > el.clientHeight + 20)
        .map((el) => {
          const style = getComputedStyle(el);
          const score = (el.querySelectorAll("[role='article'], a[href*='comment_id'], a[href*='reply_comment_id']").length * 10)
            + (/auto|scroll/i.test(style.overflowY) ? 5 : 0)
            + Math.min(el.scrollHeight - el.clientHeight, 1000) / 1000;
          return {el, score};
        })
        .sort((a, b) => b.score - a.score);
      const target = candidates[0]?.el || rootEl;
      const beforeTop = target.scrollTop || 0;
      const clientHeight = target.clientHeight || window.innerHeight;
      const scrollHeight = target.scrollHeight || document.body.scrollHeight;
      target.scrollTop = beforeTop + Math.floor(clientHeight * 0.85);
      return {
        scroll_top: target.scrollTop || 0,
        scroll_height: scrollHeight,
        client_height: clientHeight,
        scrolled: (target.scrollTop || 0) !== beforeTop
      };
    }
    """
    try:
        return await root.evaluate(script)
    except Exception:
        return {"scroll_top": None, "scroll_height": None, "client_height": None, "scrolled": False}


def _js_string(value: str) -> str:
    return repr(value)


async def _safe_locator_count(locator) -> int:
    try:
        return int(await locator.count())
    except Exception:
        return 0


def _location(locator, strategy: str, count: int) -> CommentNodeLocation:
    return CommentNodeLocation(
        locator=None if count != 1 else locator.first,
        diagnostics={
            "found": count == 1,
            "strategy": strategy,
            "matched_count": count,
            "ambiguous": count > 1,
        },
    )


def _text_excerpt(value: str, limit: int = 80) -> str:
    lines = [" ".join(line.split()) for line in (value or "").splitlines()]
    meaningful = [line for line in lines if len(line) >= 5]
    candidate = meaningful[-1] if meaningful else " ".join((value or "").split())
    return candidate[:limit]


def _css_attr_value(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


async def _comment_id_nearest_article_count(
    page,
    comment_id: str,
    comment_text: str | None = None,
) -> int:
    if not hasattr(page, "evaluate"):
        return 0
    script = """
    ({ commentId, commentText }) => {
      const textNeedle = (commentText || '').replace(/\\s+/g, ' ').trim().slice(0, 80);
      const textOf = (el) => (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
      const articles = [];
      const addArticle = (article) => {
        if (!article || articles.includes(article)) return;
        if (textNeedle && !textOf(article).includes(textNeedle)) return;
        articles.push(article);
      };
      Array.from(document.querySelectorAll('[role="article"]')).forEach((article) => {
        if (article.getAttribute('data-commentid') === commentId || article.id === commentId) {
          addArticle(article);
        }
      });
      Array.from(document.querySelectorAll('a[href]')).forEach((link) => {
        if (!(link.href || '').includes(commentId)) return;
        addArticle(link.closest('[role="article"]'));
      });
      return articles.length;
    }
    """
    try:
        return int(await page.evaluate(script, {"commentId": comment_id, "commentText": comment_text}))
    except Exception:
        return 0
