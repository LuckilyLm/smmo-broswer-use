from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .comments import count_comment_candidates, expand_comments, find_comment_root, locate_comment_node
from .diagnostics import write_json
from .login_state import detect_login_state


REPLY_LABEL_RE = re.compile(r"^(reply|回复|回覆)$", re.I)
SEND_LABEL_RE = re.compile(r"^(send|post|reply|发送|发布|回复|回覆)$", re.I)
DEFAULT_REPLY_HISTORY_PATH = Path("artifacts/facebook_leads/reply_history.jsonl")


@dataclass(frozen=True)
class ReplyRequest:
    source_content_url: str
    direct_comment_url: str | None
    comment_id: str | None
    author_name: str | None
    comment_text: str | None
    fingerprint: str | None
    reply_text: str
    confirm_send: bool = False
    yes: bool = False
    keep_filled: bool = False
    allow_duplicate: bool = False
    lead_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReplyResult:
    success: bool
    stage: str
    located: bool
    locate_strategy: str | None
    matched_count: int
    reply_clicked: bool
    input_found: bool
    text_filled: bool
    sent: bool
    dry_run: bool
    source_content_url: str
    direct_comment_url: str | None
    comment_id: str | None
    reply_text: str
    final_url: str | None
    timing: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    error_type: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocatorSearchResult:
    locator: Any | None
    strategy: str
    matched_count: int


async def reply_to_comment(
    page,
    request: ReplyRequest,
    *,
    artifacts_dir: str | Path = "artifacts/facebook_leads/replies",
    history_path: str | Path = DEFAULT_REPLY_HISTORY_PATH,
) -> dict[str, Any]:
    started = time.perf_counter()
    dry_run = not (request.confirm_send and request.yes)
    diagnostics: dict[str, Any] = {
        "dry_run": dry_run,
        "confirm_send": request.confirm_send,
        "yes": request.yes,
        "no_llm": True,
        "agent_called": False,
        "closed_remote_chromium": False,
        "close_called": False,
    }
    if request.confirm_send and not request.yes:
        diagnostics["send_gate"] = "真实发送需要同时提供 --confirm-send --yes"

    duplicate = find_successful_duplicate(
        history_path,
        comment_id=request.comment_id,
        fingerprint=request.fingerprint,
    )
    if duplicate and not dry_run and not request.allow_duplicate:
        result = _result(
            request,
            success=False,
            stage="duplicate_check",
            dry_run=dry_run,
            diagnostics={**diagnostics, "duplicate": duplicate},
            error_type="duplicate_reply",
            error="A successful reply already exists for this comment_id or fingerprint",
        )
        return write_reply_result(request, result, artifacts_dir, started)

    try:
        await open_target_comment(page, request)
        diagnostics["url_after_open"] = getattr(page, "url", None)
        location = await _locate_for_reply(page, request)
        if int(location.diagnostics.get("matched_count") or 0) != 1:
            diagnostics["locate_before_expand"] = location.diagnostics
            diagnostics["comment_expand"] = await expand_comments(page, max_expand_clicks=5)
            location = await _locate_for_reply(page, request)
        locate_diag = location.diagnostics
        diagnostics["locate"] = locate_diag
        matched_count = int(locate_diag.get("matched_count") or 0)
        if matched_count != 1 or location.locator is None:
            result = _result(
                request,
                success=False,
                stage="locate_comment",
                dry_run=dry_run,
                located=False,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                diagnostics={**diagnostics, "ambiguous": bool(locate_diag.get("ambiguous"))},
                error_type="ambiguous_comment" if locate_diag.get("ambiguous") else "comment_not_found",
                error="Target comment was not uniquely located",
            )
            return write_reply_result(request, result, artifacts_dir, started)

        before_snapshot = await snapshot_visible_textboxes(page)
        reply_action = await find_reply_action(location.locator)
        diagnostics["reply_action"] = {
            "strategy": reply_action.strategy,
            "matched_count": reply_action.matched_count,
        }
        if reply_action.matched_count != 1 or reply_action.locator is None:
            result = _result(
                request,
                success=False,
                stage="find_reply_action",
                dry_run=dry_run,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                diagnostics=diagnostics,
                error_type="reply_action_not_unique",
                error="Reply action was not uniquely found inside the target comment node",
            )
            return write_reply_result(request, result, artifacts_dir, started)

        await reply_action.locator.click(timeout=5000)
        try:
            await page.wait_for_timeout(800)
        except Exception:
            pass
        reply_input = await find_reply_input(page, location.locator, before_snapshot)
        diagnostics["reply_input"] = {
            "strategy": reply_input.strategy,
            "matched_count": reply_input.matched_count,
        }
        if reply_input.matched_count != 1 or reply_input.locator is None:
            result = _result(
                request,
                success=False,
                stage="find_reply_input",
                dry_run=dry_run,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                diagnostics=diagnostics,
                error_type="reply_input_not_unique",
                error="Reply input was not uniquely found",
            )
            return write_reply_result(request, result, artifacts_dir, started)

        await fill_reply_input(reply_input.locator, request.reply_text)
        filled_text = await read_input_text(reply_input.locator)
        diagnostics["filled_text_matches"] = filled_text == request.reply_text
        if filled_text != request.reply_text:
            result = _result(
                request,
                success=False,
                stage="fill_reply_input",
                dry_run=dry_run,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                input_found=True,
                text_filled=False,
                diagnostics=diagnostics,
                error_type="reply_text_mismatch",
                error="Filled reply text does not match requested text",
            )
            return write_reply_result(request, result, artifacts_dir, started)

        if dry_run:
            if not request.keep_filled:
                await clear_reply_input(reply_input.locator)
                diagnostics["dry_run_cleared"] = True
            result = _result(
                request,
                success=True,
                stage="dry_run_complete",
                dry_run=True,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                input_found=True,
                text_filled=True,
                sent=False,
                diagnostics=diagnostics,
            )
            return write_reply_result(request, result, artifacts_dir, started)

        safety = await pre_send_safety_check(page, request, reply_input.locator)
        diagnostics["pre_send_safety"] = safety
        if not safety["ok"]:
            result = _result(
                request,
                success=False,
                stage="pre_send_safety",
                dry_run=False,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                input_found=True,
                text_filled=True,
                diagnostics=diagnostics,
                error_type="pre_send_safety_failed",
                error=safety["reason"],
            )
            return write_reply_result(request, result, artifacts_dir, started)

        send_action = await find_send_action(page, reply_input.locator)
        diagnostics["send_action"] = {
            "strategy": send_action.strategy,
            "matched_count": send_action.matched_count,
        }
        if send_action.matched_count != 1 or send_action.locator is None:
            result = _result(
                request,
                success=False,
                stage="find_send_action",
                dry_run=False,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                input_found=True,
                text_filled=True,
                diagnostics=diagnostics,
                error_type="send_action_not_unique",
                error="Send action was not uniquely found",
            )
            return write_reply_result(request, result, artifacts_dir, started)

        await send_action.locator.click(timeout=5000)
        try:
            await page.wait_for_timeout(1500)
        except Exception:
            pass
        verification = await verify_reply_sent(page, request, reply_input.locator)
        diagnostics["verification"] = verification
        result = _result(
            request,
            success=True,
            stage="sent",
            dry_run=False,
            located=True,
            locate_strategy=locate_diag.get("strategy"),
            matched_count=matched_count,
            reply_clicked=True,
            input_found=True,
            text_filled=True,
            sent=True,
            diagnostics=diagnostics,
        )
        append_reply_history(history_path, request, verified=bool(verification.get("verified")))
        return write_reply_result(request, result, artifacts_dir, started)
    except Exception as exc:
        result = _result(
            request,
            success=False,
            stage="error",
            dry_run=dry_run,
            diagnostics=diagnostics,
            error_type=exc.__class__.__name__,
            error=str(exc),
        )
        return write_reply_result(request, result, artifacts_dir, started)


async def open_target_comment(page, request: ReplyRequest) -> None:
    target_url = request.direct_comment_url or request.source_content_url
    if target_url and getattr(page, "url", None) != target_url:
        await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
    await wait_for_comment_ready(page, request)


async def wait_for_comment_ready(page, request: ReplyRequest, timeout_ms: int = 10000) -> None:
    interval_ms = 1000
    elapsed_ms = 0
    excerpt = _comment_text_excerpt(request.comment_text)
    while elapsed_ms <= timeout_ms:
        if excerpt and await _body_contains(page, excerpt):
            return
        try:
            root = await find_comment_root(page)
            if await count_comment_candidates(root.root) > 0:
                return
        except Exception:
            pass
        try:
            await page.wait_for_timeout(interval_ms)
        except Exception:
            return
        elapsed_ms += interval_ms


async def _locate_for_reply(page, request: ReplyRequest):
    return await locate_comment_node(
        page,
        comment_id=request.comment_id,
        direct_comment_url=request.direct_comment_url,
        author_name=request.author_name,
        comment_text=request.comment_text,
    )


async def find_reply_action(comment_node) -> LocatorSearchResult:
    if hasattr(comment_node, "find_reply_action"):
        return await comment_node.find_reply_action()
    candidates = [
        ("role_button", _role_button_locator(comment_node, REPLY_LABEL_RE)),
        ("aria_label", comment_node.locator("[aria-label='Reply'], [aria-label='回复'], [aria-label='回覆']")),
        ("text_clickable", comment_node.locator("span, div").filter(has_text=REPLY_LABEL_RE)),
    ]
    return await _first_unique_locator(candidates)


async def snapshot_visible_textboxes(page) -> list[str]:
    if hasattr(page, "snapshot_visible_textboxes"):
        return list(await page.snapshot_visible_textboxes())
    script = """
    () => Array.from(document.querySelectorAll('[role="textbox"], textarea, [contenteditable="true"]'))
      .filter((el) => {
        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
      })
      .map((el, index) => el.getAttribute('data-lexical-editor')
        || el.getAttribute('aria-label')
        || el.getAttribute('placeholder')
        || el.id
        || `${el.tagName}:${index}:${(el.innerText || el.value || '').slice(0, 30)}`);
    """
    try:
        return list(await page.evaluate(script))
    except Exception:
        return []


async def find_reply_input(page, comment_node, before_snapshot: list[str]) -> LocatorSearchResult:
    if hasattr(page, "find_reply_input"):
        return await page.find_reply_input(comment_node=comment_node, before_snapshot=before_snapshot)
    focused = page.locator("[role='textbox']:focus, textarea:focus, [contenteditable='true']:focus")
    focused_count = await _safe_count(focused)
    if focused_count == 1:
        return LocatorSearchResult(focused.first, "focused_textbox", 1)

    near = comment_node.locator("[role='textbox'], textarea, [contenteditable='true']")
    near_count = await _safe_count(near)
    if near_count == 1:
        return LocatorSearchResult(near.first, "comment_node_textbox", 1)

    after_snapshot = await snapshot_visible_textboxes(page)
    if len(after_snapshot) > len(before_snapshot):
        all_textboxes = page.locator("[role='textbox'], textarea, [contenteditable='true']")
        count = await _safe_count(all_textboxes)
        if count == 1:
            return LocatorSearchResult(all_textboxes.first, "new_visible_textbox", 1)
    return LocatorSearchResult(None, "not_found", 0)


async def fill_reply_input(locator, text: str) -> None:
    if hasattr(locator, "fill"):
        await locator.fill(text)
        return
    await locator.click()


async def clear_reply_input(locator) -> None:
    await fill_reply_input(locator, "")


async def read_input_text(locator) -> str:
    if hasattr(locator, "input_value"):
        try:
            return await locator.input_value(timeout=1000)
        except Exception:
            pass
    if hasattr(locator, "inner_text"):
        try:
            return await locator.inner_text(timeout=1000)
        except Exception:
            pass
    return ""


async def pre_send_safety_check(page, request: ReplyRequest, input_locator) -> dict[str, Any]:
    if not _is_facebook_url(getattr(page, "url", "")):
        return {"ok": False, "reason": "current page is not Facebook"}
    login_state = await detect_login_state(page)
    if login_state in {"checkpoint", "captcha", "logged_out"}:
        return {"ok": False, "reason": f"login state blocks send: {login_state}"}
    current_text = await read_input_text(input_locator)
    if current_text != request.reply_text:
        return {"ok": False, "reason": "reply input text changed before send"}
    location = await locate_comment_node(
        page,
        comment_id=request.comment_id,
        direct_comment_url=request.direct_comment_url,
        author_name=request.author_name,
        comment_text=request.comment_text,
    )
    if int(location.diagnostics.get("matched_count") or 0) != 1:
        return {"ok": False, "reason": "target comment is no longer uniquely located"}
    return {"ok": True, "reason": None, "login_state": login_state}


async def find_send_action(page, input_locator) -> LocatorSearchResult:
    if hasattr(page, "find_send_action"):
        return await page.find_send_action(input_locator)
    candidates = [
        ("focused_submit_button", page.get_by_role("button", name=SEND_LABEL_RE)),
        ("aria_submit_button", page.locator("[aria-label='Send'], [aria-label='Post'], [aria-label='发送'], [aria-label='发布']")),
    ]
    return await _first_unique_locator(candidates)


async def verify_reply_sent(page, request: ReplyRequest, input_locator) -> dict[str, Any]:
    if hasattr(page, "verify_reply_sent"):
        return await page.verify_reply_sent(request=request, input_locator=input_locator)
    evidence: dict[str, Any] = {}
    current_text = await read_input_text(input_locator)
    if current_text == "":
        evidence["input_cleared"] = True
    try:
        body = await page.locator("body").inner_text(timeout=3000)
        if request.reply_text and request.reply_text in body:
            return {"verified": True, "strategy": "reply_text_visible", "evidence": {"reply_text_visible": True}}
    except Exception:
        pass
    return {"verified": False, "strategy": "unconfirmed", "evidence": evidence}


def find_successful_duplicate(
    history_path: str | Path,
    *,
    comment_id: str | None,
    fingerprint: str | None,
) -> dict[str, Any] | None:
    path = Path(history_path)
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not item.get("success"):
            continue
        if comment_id and item.get("comment_id") == comment_id:
            return item
        if fingerprint and item.get("fingerprint") == fingerprint:
            return item
    return None


def append_reply_history(history_path: str | Path, request: ReplyRequest, *, verified: bool) -> None:
    path = Path(history_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "success": True,
        "fingerprint": request.fingerprint,
        "comment_id": request.comment_id,
        "source_content_url": request.source_content_url,
        "reply_text": request.reply_text,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "verified": verified,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_reply_request_from_lead_report(
    lead_report_path: str | Path,
    lead_index: int,
    reply_text: str | None,
    *,
    use_suggested_reply: bool = False,
    confirm_send: bool = False,
    yes: bool = False,
    keep_filled: bool = False,
    allow_duplicate: bool = False,
) -> ReplyRequest:
    if lead_index < 1:
        raise ValueError("--lead-index is 1-based and must be >= 1")
    data = json.loads(Path(lead_report_path).read_text(encoding="utf-8"))
    leads = _ordered_report_leads(data)
    if lead_index > len(leads):
        raise ValueError(f"--lead-index {lead_index} is out of range; report has {len(leads)} leads")
    lead = leads[lead_index - 1]
    resolved_reply_text = reply_text
    if use_suggested_reply:
        resolved_reply_text = (lead.get("llm_review") or {}).get("suggested_reply") or lead.get("final_suggested_reply")
        if not resolved_reply_text:
            raise ValueError("--use-suggested-reply requested but selected lead has no suggested_reply")
    if not resolved_reply_text:
        raise ValueError("--reply-text is required unless --use-suggested-reply is available")
    return ReplyRequest(
        source_content_url=lead["source_content_url"],
        direct_comment_url=lead.get("direct_comment_url"),
        comment_id=lead.get("comment_id"),
        author_name=lead.get("author_name"),
        comment_text=lead.get("comment_text"),
        fingerprint=lead.get("comment_fingerprint"),
        reply_text=resolved_reply_text,
        confirm_send=confirm_send,
        yes=yes,
        keep_filled=keep_filled,
        allow_duplicate=allow_duplicate,
        lead_index=lead_index,
    )


def write_reply_result(
    request: ReplyRequest,
    result: ReplyResult,
    artifacts_dir: str | Path,
    started: float,
) -> dict[str, Any]:
    result.timing["total_ms"] = int((time.perf_counter() - started) * 1000)
    if result.final_url is None:
        result.final_url = result.diagnostics.get("url_after_open")
    output_dir = Path(artifacts_dir) / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "reply_result.json"
    payload = {
        "request": request.to_dict(),
        "result": result.to_dict(),
        "timing": result.timing,
        "diagnostics": result.diagnostics,
    }
    write_json(result_path, payload)
    payload["paths"] = {"reply_result_json": str(result_path)}
    write_json(result_path, payload)
    return payload


def _ordered_report_leads(report: dict[str, Any]) -> list[dict[str, Any]]:
    leads = [lead for content in report.get("contents", []) for lead in content.get("leads", [])]
    level_rank = {"high": 3, "medium": 2, "low": 1, "none": 0}
    return [
        lead
        for _, lead in sorted(
            enumerate(leads),
            key=lambda item: (
                0 if item[1].get("final_is_lead") is True else 1,
                -level_rank.get(item[1].get("final_intent_level") or item[1].get("intent_level"), 0),
                -float((item[1].get("llm_review") or {}).get("confidence") or 0),
                -int(item[1].get("intent_score") or 0),
                item[0],
            ),
        )
    ]


def _result(
    request: ReplyRequest,
    *,
    success: bool,
    stage: str,
    dry_run: bool,
    located: bool = False,
    locate_strategy: str | None = None,
    matched_count: int = 0,
    reply_clicked: bool = False,
    input_found: bool = False,
    text_filled: bool = False,
    sent: bool = False,
    diagnostics: dict[str, Any] | None = None,
    error_type: str | None = None,
    error: str | None = None,
) -> ReplyResult:
    return ReplyResult(
        success=success,
        stage=stage,
        located=located,
        locate_strategy=locate_strategy,
        matched_count=matched_count,
        reply_clicked=reply_clicked,
        input_found=input_found,
        text_filled=text_filled,
        sent=sent,
        dry_run=dry_run,
        source_content_url=request.source_content_url,
        direct_comment_url=request.direct_comment_url,
        comment_id=request.comment_id,
        reply_text=request.reply_text,
        final_url=None,
        diagnostics=diagnostics or {},
        error_type=error_type,
        error=error,
    )


async def _first_unique_locator(candidates: list[tuple[str, Any]]) -> LocatorSearchResult:
    fallback_multi: LocatorSearchResult | None = None
    for strategy, locator in candidates:
        count = await _safe_count(locator)
        if count == 1:
            return LocatorSearchResult(locator.first, strategy, count)
        if count > 1 and fallback_multi is None:
            fallback_multi = LocatorSearchResult(None, strategy, count)
    return fallback_multi or LocatorSearchResult(None, "not_found", 0)


async def _safe_count(locator) -> int:
    try:
        return int(await locator.count())
    except Exception:
        return 0


def _role_button_locator(root, name_pattern: re.Pattern[str]):
    if hasattr(root, "get_by_role"):
        return root.get_by_role("button", name=name_pattern)
    return root.locator("[role='button'], button").filter(has_text=name_pattern)


def _is_facebook_url(url: str | None) -> bool:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    return host == "facebook.com" or host.endswith(".facebook.com")


async def _body_contains(page, text: str) -> bool:
    try:
        body = await page.locator("body").inner_text(timeout=1500)
        return text in body
    except Exception:
        return False


def _comment_text_excerpt(value: str | None) -> str:
    lines = [" ".join(line.split()) for line in (value or "").splitlines()]
    meaningful = [line for line in lines if len(line) >= 5]
    return (meaningful[-1] if meaningful else " ".join((value or "").split()))[:60]
