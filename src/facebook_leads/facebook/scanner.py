from __future__ import annotations

import time
from typing import Any

from .comments import count_comment_candidates, expand_comments, extract_comments, find_comment_root, wait_for_comments_loaded
from .content import open_content
from .content_metadata import extract_content_metadata
from .login_state import detect_login_state
from .models import FacebookComment, FacebookContentCandidate, FacebookScanResult
from .search import discover_content_candidates, is_candidate_content_url, search_facebook_contents


class FacebookReadOnlyGuard:
    allowed_operations = frozenset({"search", "open", "expand", "extract"})
    forbidden_operations = frozenset({"reply", "like", "follow", "message", "post"})


async def run_readonly_scan(
    page,
    keyword: str | None,
    content_limit: int = 5,
    comment_limit: int = 100,
    max_scrolls: int = 5,
    max_expand_clicks: int = 20,
    current_page_only: bool = False,
) -> FacebookScanResult:
    started = time.perf_counter()
    timing: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {"read_only": True}
    contents: list[FacebookContentCandidate] = []
    comments: list[FacebookComment] = []
    stage = "init"
    login_state = "unknown"

    try:
        stage = "login_check"
        t0 = time.perf_counter()
        login_state = await detect_login_state(page)
        timing["login_check_ms"] = _elapsed_ms(t0)
        active_url = getattr(page, "url", None)
        if login_state in {"logged_out", "checkpoint", "captcha"}:
            return _result(False, "stopped_login_state", keyword, login_state, active_url, contents, comments, timing, diagnostics)

        if current_page_only:
            if "facebook.com" not in (active_url or ""):
                return _result(
                    False,
                    "not_facebook_page",
                    keyword,
                    login_state,
                    active_url,
                    contents,
                    comments,
                    timing,
                    diagnostics,
                    "ValueError",
                    "current-page-only requires an open Facebook page",
                )
            if not is_candidate_content_url(active_url or ""):
                return _result(
                    False,
                    "not_facebook_content_page",
                    keyword,
                    login_state,
                    active_url,
                    contents,
                    comments,
                    timing,
                    diagnostics,
                    "ValueError",
                    "current-page-only requires a Facebook post, Reel, video, or permalink URL",
                )
            contents = [
                FacebookContentCandidate(
                    url=active_url,
                    content_type="unknown",
                    discovered_from="current_page",
                    discovery_index=0,
                )
            ]
        else:
            if not keyword:
                raise ValueError("--keyword is required unless --current-page-only is used")
            stage = "search"
            t0 = time.perf_counter()
            contents = await search_facebook_contents(page, keyword, limit=content_limit, max_scrolls=max_scrolls)
            timing["search_ms"] = _elapsed_ms(t0)
            timing["content_discovery_ms"] = timing["search_ms"]

        per_content = []
        seen_comments: set[str] = set()
        for index, candidate in enumerate(contents[:content_limit]):
            content_timing: dict[str, Any] = {"url": candidate.url}
            content_diag: dict[str, Any] = {
                "discovered_url": candidate.url,
                "content_type": candidate.content_type,
                "failure_stage": None,
                "timing": content_timing,
            }
            source_content_url = candidate.url
            if not current_page_only:
                stage = "content_open"
                t0 = time.perf_counter()
                open_diag = await open_content(page, candidate.url)
                content_timing["open_ms"] = _elapsed_ms(t0)
                timing["content_open_ms"] = timing.get("content_open_ms", 0) + content_timing["open_ms"]
                content_diag["open"] = open_diag
                content_diag["final_url"] = open_diag.get("final_url")
                source_content_url = open_diag.get("final_url") or candidate.url
            else:
                content_diag["final_url"] = source_content_url

            stage = "content_metadata"
            enriched_candidate, metadata_diag = await extract_content_metadata(page, candidate)
            contents[index] = enriched_candidate
            candidate = enriched_candidate
            content_diag.update(metadata_diag)
            source_content_url = metadata_diag.get("final_url") or source_content_url

            stage = "comment_expand"
            root_before = await find_comment_root(page)
            before_count = await count_comment_candidates(root_before.root)
            content_diag["comment_root_type_before"] = root_before.root_type
            content_diag["comment_candidate_count_before"] = before_count
            t0 = time.perf_counter()
            expand_diag = await expand_comments(page, max_expand_clicks=max_expand_clicks)
            content_timing["expand_ms"] = _elapsed_ms(t0)
            content_timing["panel_ms"] = expand_diag.get("comment_panel", {}).get("elapsed_ms", 0)
            timing["comment_expand_ms"] = timing.get("comment_expand_ms", 0) + content_timing["expand_ms"]
            diagnostics.update(expand_diag)
            content_diag["comment_panel"] = expand_diag.get("comment_panel")
            content_diag["comment_root_type"] = expand_diag.get("comment_root_type")
            content_diag["comment_candidate_count_after_panel"] = expand_diag.get("comment_panel", {}).get("after", {}).get("count")
            content_diag["comment_candidate_count_after_scroll"] = expand_diag.get("comment_candidate_count_after_scroll")
            content_diag["comment_scroll"] = expand_diag.get("comment_scroll")

            stage = "comments_wait"
            t0 = time.perf_counter()
            waited_count = await wait_for_comments_loaded(page, timeout_ms=15000, min_count=1)
            content_timing["wait_comments_ms"] = _elapsed_ms(t0)
            content_diag["comment_candidate_count_after_wait"] = waited_count

            stage = "comment_extract"
            root_after = await find_comment_root(page)
            t0 = time.perf_counter()
            extracted = await extract_comments(page, source_content_url, root=root_after.root, limit=comment_limit)
            content_timing["extract_ms"] = _elapsed_ms(t0)
            timing["comment_extract_ms"] = timing.get("comment_extract_ms", 0) + content_timing["extract_ms"]
            for comment in extracted:
                if comment.fingerprint in seen_comments:
                    diagnostics["duplicate_comments_removed"] = diagnostics.get("duplicate_comments_removed", 0) + 1
                    continue
                seen_comments.add(comment.fingerprint)
                comments.append(comment)
                if len(comments) >= comment_limit:
                    break
            content_timing["comment_count"] = len(extracted)
            content_diag["extracted_comment_count"] = len(extracted)
            if not extracted:
                content_diag["failure_stage"] = "comments_extract" if waited_count > 0 else "comments_wait"
            per_content.append(content_diag)
            if len(comments) >= comment_limit:
                break

        diagnostics["per_content"] = per_content
        timing["total_ms"] = _elapsed_ms(started)
        return _result(True, "completed", keyword, login_state, getattr(page, "url", None), contents, comments, timing, diagnostics)
    except Exception as exc:
        timing["total_ms"] = _elapsed_ms(started)
        return _result(
            False,
            stage,
            keyword,
            login_state,
            getattr(page, "url", None),
            contents,
            comments,
            timing,
            diagnostics,
            type(exc).__name__,
            str(exc),
        )


def _result(
    success: bool,
    stage: str,
    keyword: str | None,
    login_state: str,
    active_page_url: str | None,
    contents,
    comments,
    timing,
    diagnostics,
    error_type: str | None = None,
    error: str | None = None,
) -> FacebookScanResult:
    timing.setdefault("browser_init_ms", 0)
    timing.setdefault("get_page_ms", 0)
    timing.setdefault("search_ms", 0)
    timing.setdefault("content_discovery_ms", 0)
    timing.setdefault("content_open_ms", 0)
    timing.setdefault("comment_expand_ms", 0)
    timing.setdefault("comment_extract_ms", 0)
    timing.setdefault("total_ms", 0)
    diagnostics.setdefault("duplicate_comments_removed", 0)
    return FacebookScanResult(
        success=success,
        stage=stage,
        keyword=keyword,
        login_state=login_state,
        active_page_url=active_page_url,
        contents=contents,
        comments=comments,
        timing=timing,
        diagnostics=diagnostics,
        error_type=error_type,
        error=error,
    )


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
