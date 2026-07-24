from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

from .comments import count_comment_candidates, expand_comments, extract_comments, find_comment_root, wait_for_comments_loaded
from .content import open_content
from .diagnostics import write_json
from .content_metadata import extract_content_metadata
from .login_state import detect_login_state
from .models import FacebookComment, FacebookContentCandidate, FacebookLoginState, FacebookScanResult
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
    incremental_output_path: str | Path | None = None,
    resume_payload: dict[str, Any] | None = None,
) -> FacebookScanResult:
    started = time.perf_counter()
    timing: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {"read_only": True}
    discovered_contents: list[FacebookContentCandidate] = []
    contents: list[FacebookContentCandidate] = _content_candidates_from_payload(resume_payload)
    comments: list[FacebookComment] = _comments_from_payload(resume_payload)
    stage = "init"
    login_state = "unknown"
    per_content = list(((resume_payload or {}).get("diagnostics") or {}).get("per_content") or [])
    content_failures = list(((resume_payload or {}).get("diagnostics") or {}).get("content_failures") or [])
    seen_comments: set[str] = {comment.fingerprint for comment in comments if comment.fingerprint}
    successful_urls = {_normalize_url(item.url) for item in contents}

    try:
        stage = "login_check"
        t0 = time.perf_counter()
        login_state = await detect_login_state(page)
        timing["login_check_ms"] = _elapsed_ms(t0)
        active_url = getattr(page, "url", None)
        if login_state in {"logged_out", "checkpoint", "captcha"}:
            return _result(False, "stopped_login_state", keyword, login_state, active_url, contents, comments, timing, diagnostics, discovered_contents=discovered_contents)

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
                    discovered_contents=discovered_contents,
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
                    discovered_contents=discovered_contents,
                )
            if active_url:
                discovered_contents = [
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
            discovered_contents = await search_facebook_contents(page, keyword, limit=content_limit, max_scrolls=max_scrolls)
            timing["search_ms"] = _elapsed_ms(t0)
            timing["content_discovery_ms"] = timing["search_ms"]
        diagnostics["discovered_contents_count"] = len(discovered_contents)
        _persist_scan_snapshot(
            incremental_output_path,
            True,
            "discovered",
            keyword,
            login_state,
            getattr(page, "url", None),
            discovered_contents,
            contents,
            comments,
            timing,
            diagnostics,
            per_content,
            content_failures,
        )

        for index, candidate in enumerate(discovered_contents[:content_limit]):
            if _normalize_url(candidate.url) in successful_urls:
                diagnostics["resume_skipped_success_count"] = diagnostics.get("resume_skipped_success_count", 0) + 1
                continue
            content_timing: dict[str, Any] = {"url": candidate.url}
            content_diag: dict[str, Any] = {
                "discovered_url": candidate.url,
                "content_type": candidate.content_type,
                "failure_stage": None,
                "timing": content_timing,
            }
            source_content_url = candidate.url
            try:
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
                content_diag["skipped"] = False
                per_content.append(content_diag)
                contents.append(candidate)
                successful_urls.add(_normalize_url(candidate.url))
            except Exception as exc:
                if await _is_fatal_scan_error(page, exc):
                    raise
                failure = _content_failure(candidate, stage, exc)
                content_diag.update(failure)
                per_content.append(content_diag)
                content_failures.append(failure)
            _persist_scan_snapshot(
                incremental_output_path,
                True,
                "content_scanned",
                keyword,
                login_state,
                getattr(page, "url", None),
                discovered_contents,
                contents,
                comments,
                timing,
                diagnostics,
                per_content,
                content_failures,
                current_index=index,
            )
            if len(comments) >= comment_limit:
                break

        diagnostics["per_content"] = per_content
        diagnostics["content_failures"] = content_failures
        diagnostics["content_failure_count"] = len(content_failures)
        diagnostics["content_success_count"] = len(contents)
        diagnostics["content_skipped_count"] = len(content_failures)
        timing["total_ms"] = _elapsed_ms(started)
        status = "completed"
        if content_failures and contents:
            status = "partial"
        if not contents:
            return _result(False, "failed", keyword, login_state, getattr(page, "url", None), contents, comments, timing, diagnostics, "RuntimeError", "no content scanned successfully", discovered_contents=discovered_contents)
        return _result(True, status, keyword, login_state, getattr(page, "url", None), contents, comments, timing, diagnostics, discovered_contents=discovered_contents)
    except Exception as exc:
        timing["total_ms"] = _elapsed_ms(started)
        return _result(
            False,
            "failed",
            keyword,
            login_state,
            getattr(page, "url", None),
            contents,
            comments,
            timing,
            diagnostics,
            type(exc).__name__,
            str(exc),
            discovered_contents=discovered_contents,
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
    discovered_contents=None,
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
    content_failure_count = int(diagnostics.get("content_failure_count") or len(diagnostics.get("content_failures") or []))
    content_success_count = int(diagnostics.get("content_success_count") or len(contents))
    status = stage if stage in {"completed", "partial", "failed"} else ("completed" if success else "failed")
    normalized_login_state = cast(FacebookLoginState, login_state) if login_state in {"logged_in", "logged_out", "checkpoint", "captcha", "unknown"} else "unknown"
    return FacebookScanResult(
        success=success,
        stage=stage,
        status=status,
        partial=status == "partial",
        keyword=keyword,
        login_state=normalized_login_state,
        active_page_url=active_page_url,
        discovered_contents=discovered_contents or [],
        contents=contents,
        comments=comments,
        timing=timing,
        diagnostics=diagnostics,
        error_type=error_type,
        error=error,
        content_success_count=content_success_count,
        content_failure_count=content_failure_count,
        content_skipped_count=int(diagnostics.get("content_skipped_count") or content_failure_count),
    )


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _persist_scan_snapshot(
    path: str | Path | None,
    success: bool,
    stage: str,
    keyword: str | None,
    login_state: str,
    active_page_url: str | None,
    discovered_contents: list[FacebookContentCandidate],
    contents: list[FacebookContentCandidate],
    comments: list[FacebookComment],
    timing: dict[str, Any],
    diagnostics: dict[str, Any],
    per_content: list[dict[str, Any]],
    content_failures: list[dict[str, Any]],
    *,
    current_index: int | None = None,
) -> None:
    if not path:
        return
    snapshot_diag = dict(diagnostics)
    snapshot_diag["per_content"] = per_content
    snapshot_diag["content_failures"] = content_failures
    snapshot_diag["content_failure_count"] = len(content_failures)
    snapshot_diag["content_success_count"] = len(contents)
    snapshot_diag["content_skipped_count"] = len(content_failures)
    if current_index is not None:
        snapshot_diag["current_index"] = current_index
    snapshot = _result(
        success,
        stage,
        keyword,
        login_state,
        active_page_url,
        contents,
        comments,
        dict(timing),
        snapshot_diag,
        discovered_contents=discovered_contents,
    ).to_dict()
    write_json(path, snapshot)


def _content_failure(candidate: FacebookContentCandidate, stage: str, exc: Exception) -> dict[str, Any]:
    return {
        "url": candidate.url,
        "content_type": candidate.content_type,
        "stage": stage,
        "failure_stage": stage,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "retry_count": 1,
        "skipped": True,
    }


async def _is_fatal_scan_error(page, exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    fatal_markers = (
        "target closed",
        "browser closed",
        "browser has been closed",
        "connection closed",
        "cdp",
        "disconnected",
    )
    if any(marker in text for marker in fatal_markers):
        return True
    try:
        state = await detect_login_state(page)
    except Exception:
        return False
    return state in {"logged_out", "checkpoint", "captcha"}


def _content_candidates_from_payload(payload: dict[str, Any] | None) -> list[FacebookContentCandidate]:
    if not payload:
        return []
    return [_candidate_from_dict(item) for item in payload.get("contents") or []]


def _candidate_from_dict(item: dict[str, Any]) -> FacebookContentCandidate:
    return FacebookContentCandidate(
        url=item.get("url") or "",
        content_type=item.get("content_type"),
        text_preview=item.get("text_preview"),
        author_name=item.get("author_name"),
        discovered_from=item.get("discovered_from"),
        discovery_index=item.get("discovery_index"),
    )


def _comments_from_payload(payload: dict[str, Any] | None) -> list[FacebookComment]:
    if not payload:
        return []
    comments = []
    for item in payload.get("comments") or []:
        comments.append(
            FacebookComment(
                comment_id=item.get("comment_id"),
                author_name=item.get("author_name"),
                author_url=item.get("author_url"),
                text=item.get("text"),
                timestamp_text=item.get("timestamp_text"),
                comment_url=item.get("comment_url"),
                is_reply=bool(item.get("is_reply")),
                parent_comment_id=item.get("parent_comment_id"),
                source_content_url=item.get("source_content_url") or "",
                fingerprint=item.get("fingerprint") or "",
                direct_comment_url=item.get("direct_comment_url"),
                comment_id_source=item.get("comment_id_source"),
                author_extract_strategy=item.get("author_extract_strategy"),
            )
        )
    return comments


def _normalize_url(url: str | None) -> str:
    if not url:
        return ""
    return url.split("#", 1)[0].rstrip("/")
