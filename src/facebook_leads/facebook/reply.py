from __future__ import annotations

import json
import re
import hashlib
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from .comments import count_comment_candidates, expand_comments, find_comment_root, locate_comment_node
from .diagnostics import write_json
from .login_state import detect_login_state


REPLY_LABEL_RE = re.compile(r"^(reply|回复|回覆)$", re.I)
SEND_LABEL_RE = re.compile(r"^(send|post|reply|发送|发布|发布评论|发表评论|发送回复|回复|回覆)$", re.I)
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
    reply_source: str = "manual"
    send_confirmed: bool = False
    preview_only: bool = False
    verify_timeout_seconds: float = 15.0
    acceptance_test: bool = False
    plan_id: str | None = None
    batch_id: str | None = None
    plan_index: int | None = None
    batch_mode: bool = False
    target_policy: str | None = None
    ownership_status: str | None = None
    reply_allowed: bool | None = None

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
    status: str = "dry_run"
    send_action_performed: bool = False
    verified: bool = False
    verification_strategy: str | None = None
    verification_elapsed_ms: int | None = None
    already_replied: bool = False
    cancelled: bool = False
    blocking_reasons: list[str] = field(default_factory=list)
    idempotency_key: str | None = None
    reply_source: str = "manual"
    preflight: dict[str, Any] = field(default_factory=dict)
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


@dataclass(frozen=True)
class ReplyComposerSearchResult:
    locator: Any | None
    strategy: str
    matched_count: int
    depth: int | None = None


@dataclass(frozen=True)
class ReplyInteractionResult:
    location: Any
    locate_diag: dict[str, Any]
    reply_action: LocatorSearchResult
    reply_input: LocatorSearchResult
    diagnostics: dict[str, Any]
    error_type: str | None = None
    error: str | None = None


async def reply_to_comment(
    page,
    request: ReplyRequest,
    *,
    artifacts_dir: str | Path = "artifacts/facebook_leads/replies",
    history_path: str | Path = DEFAULT_REPLY_HISTORY_PATH,
) -> dict[str, Any]:
    started = time.perf_counter()
    dry_run = not (request.confirm_send and (request.yes or request.send_confirmed))
    idempotency_key = build_reply_idempotency_key(request)
    diagnostics: dict[str, Any] = {
        "dry_run": dry_run,
        "confirm_send": request.confirm_send,
        "yes": request.yes,
        "send_confirmed": request.send_confirmed,
        "reply_source": request.reply_source,
        "idempotency_key": idempotency_key,
        "no_llm": True,
        "agent_called": False,
        "closed_remote_chromium": False,
        "close_called": False,
        "acceptance_test": request.acceptance_test,
        "send_action_count": 0,
    }
    if request.yes and not request.confirm_send:
        diagnostics["send_gate"] = "真实发送需要同时提供 --confirm-send"
    if request.confirm_send and not request.yes and not request.send_confirmed:
        if request.acceptance_test:
            diagnostics["acceptance_note"] = "Acceptance test prepared but no real send confirmation provided. NO REAL SEND WAS ATTEMPTED."
        result = _result(
            request,
            success=False,
            stage="confirmation",
            status="cancelled",
            dry_run=False,
            cancelled=True,
            diagnostics={**diagnostics, "send_gate": "真实发送需要 --yes 或交互输入 SEND"},
            error_type="send_cancelled",
            error="Real send was not confirmed",
        )
        payload = write_reply_result(request, result, artifacts_dir, started)
        append_reply_history_from_result(history_path, request, result)
        return payload

    if request.reply_allowed is False and not dry_run:
        result = _result(
            request,
            success=False,
            stage="source_ownership_guard",
            status="blocked",
            dry_run=False,
            diagnostics={
                **diagnostics,
                "target_policy": request.target_policy,
                "ownership_status": request.ownership_status,
                "reply_allowed": request.reply_allowed,
            },
            error_type="source_not_allowed",
            error="Source ownership policy does not allow replying to this lead",
            blocking_reasons=["source_not_allowed"],
        )
        payload = write_reply_result(request, result, artifacts_dir, started)
        append_reply_history_from_result(history_path, request, result)
        return payload

    if not (request.reply_text or "").strip():
        result = _result(
            request,
            success=False,
            stage="preflight",
            status="blocked",
            dry_run=dry_run,
            diagnostics=diagnostics,
            error_type="empty_reply_text",
            error="Reply text is required",
            blocking_reasons=["reply_text_empty"],
        )
        payload = write_reply_result(request, result, artifacts_dir, started)
        if not dry_run:
            append_reply_history_from_result(history_path, request, result)
        return payload

    blocking_duplicate = find_blocking_reply_history(
        history_path,
        comment_id=request.comment_id,
        fingerprint=request.fingerprint,
        idempotency_key=idempotency_key,
        reply_text=request.reply_text,
    )
    if blocking_duplicate and not dry_run and not request.allow_duplicate:
        duplicate_status = blocking_duplicate.get("block_status")
        blocked_unverified = duplicate_status == "blocked_unverified_previous_attempt"
        result = _result(
            request,
            success=False,
            stage="duplicate_check",
            status=duplicate_status or "duplicate",
            dry_run=dry_run,
            already_replied=True,
            diagnostics={**diagnostics, "duplicate": blocking_duplicate},
            error_type="unverified_previous_attempt" if blocked_unverified else "duplicate_reply",
            error=(
                "Previous send action was performed but verification failed. Check Facebook manually before retrying."
                if blocked_unverified
                else "A verified reply already exists for this comment and reply text"
            ),
            blocking_reasons=["unverified_previous_attempt"] if blocked_unverified else ["duplicate_history"],
        )
        payload = write_reply_result(request, result, artifacts_dir, started)
        append_reply_history_from_result(history_path, request, result)
        return payload

    try:
        if request.preview_only and page is None:
            if request.acceptance_test:
                diagnostics["acceptance_note"] = "Acceptance test preview only. NO REAL SEND WAS ATTEMPTED."
            result = _result(
                request,
                success=True,
                stage="preview_only",
                status="ready",
                dry_run=True,
                diagnostics=diagnostics,
            )
            return write_reply_result(request, result, artifacts_dir, started)

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
                status="blocked",
                dry_run=dry_run,
                located=False,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                diagnostics={**diagnostics, "ambiguous": bool(locate_diag.get("ambiguous"))},
                error_type="ambiguous_comment" if locate_diag.get("ambiguous") else "comment_not_found",
                error="Target comment was not uniquely located",
                blocking_reasons=["comment_not_unique" if locate_diag.get("ambiguous") else "comment_not_found"],
            )
            payload = write_reply_result(request, result, artifacts_dir, started)
            if not dry_run:
                append_reply_history_from_result(history_path, request, result)
            return payload

        before_snapshot = await snapshot_visible_textboxes(page)
        interaction = await click_reply_action_with_recovery(page, request, location, locate_diag, before_snapshot)
        diagnostics.update(interaction.diagnostics)
        location = interaction.location
        locate_diag = interaction.locate_diag
        matched_count = int(locate_diag.get("matched_count") or 0)
        reply_action = interaction.reply_action
        reply_input = interaction.reply_input
        if interaction.error_type:
            stage = "find_reply_action" if interaction.error_type == "reply_action_not_unique" else "click_reply_action"
            result = _result(
                request,
                success=False,
                stage=stage,
                status="blocked",
                dry_run=dry_run,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                diagnostics=diagnostics,
                error_type=interaction.error_type,
                error=interaction.error,
                blocking_reasons=[interaction.error_type],
            )
            payload = write_reply_result(request, result, artifacts_dir, started)
            if not dry_run:
                append_reply_history_from_result(history_path, request, result)
            return payload
        if reply_input.matched_count != 1 or reply_input.locator is None:
            result = _result(
                request,
                success=False,
                stage="find_reply_input",
                status="blocked",
                dry_run=dry_run,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                diagnostics=diagnostics,
                error_type="reply_input_not_unique",
                error="Reply input was not uniquely found",
                blocking_reasons=["reply_input_not_unique"],
            )
            payload = write_reply_result(request, result, artifacts_dir, started)
            if not dry_run:
                append_reply_history_from_result(history_path, request, result)
            return payload

        if request.preview_only:
            existing_draft_text = await read_input_text(reply_input.locator)
            diagnostics["existing_draft_text"] = existing_draft_text
            diagnostics["ignored_existing_draft"] = _is_ignorable_existing_draft(existing_draft_text, request)
            diagnostics["reuse_existing_draft"] = existing_draft_text == request.reply_text if existing_draft_text else False
            composer = await find_reply_composer(page, reply_input.locator)
            diagnostics["reply_composer_found"] = composer.locator is not None and composer.matched_count == 1
            diagnostics["reply_composer_strategy"] = composer.strategy
            diagnostics["reply_composer_depth"] = composer.depth
            send_action = (
                await find_send_action(page, reply_input.locator, composer=composer.locator)
                if composer.locator is not None and composer.matched_count == 1
                else LocatorSearchResult(None, "reply_composer_required", 0)
            )
            diagnostics["composer_send_action_matched_count"] = send_action.matched_count
            diagnostics["send_action"] = {
                "strategy": send_action.strategy,
                "matched_count": send_action.matched_count,
            }
            result = _result(
                request,
                success=composer.matched_count == 1 and send_action.matched_count == 1,
                stage="preview_only",
                status="ready" if composer.matched_count == 1 and send_action.matched_count == 1 else "blocked",
                dry_run=True,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                input_found=True,
                text_filled=False,
                sent=False,
                diagnostics=diagnostics,
                error_type=None if composer.matched_count == 1 and send_action.matched_count == 1 else "preview_scoped_send_not_ready",
                error=None if composer.matched_count == 1 and send_action.matched_count == 1 else "Scoped composer or send action was not uniquely found",
                blocking_reasons=[] if composer.matched_count == 1 and send_action.matched_count == 1 else ["preview_scoped_send_not_ready"],
            )
            return write_reply_result(request, result, artifacts_dir, started)

        existing_draft_text = await read_input_text(reply_input.locator)
        diagnostics["existing_draft_text"] = existing_draft_text
        diagnostics["reuse_existing_draft"] = False
        if not dry_run and _is_ignorable_existing_draft(existing_draft_text, request):
            diagnostics["ignored_existing_draft"] = True
            existing_draft_text = ""
        if not dry_run and existing_draft_text:
            if existing_draft_text == request.reply_text:
                diagnostics["reuse_existing_draft"] = True
            else:
                result = _result(
                    request,
                    success=False,
                    stage="existing_draft_check",
                    status="blocked",
                    dry_run=False,
                    located=True,
                    locate_strategy=locate_diag.get("strategy"),
                    matched_count=matched_count,
                    reply_clicked=True,
                    input_found=True,
                    text_filled=False,
                    diagnostics=diagnostics,
                    error_type="unexpected_existing_draft",
                    error="Reply input already contains different draft text",
                    blocking_reasons=["unexpected_existing_draft"],
                )
                payload = write_reply_result(request, result, artifacts_dir, started)
                append_reply_history_from_result(history_path, request, result)
                return payload
        if not diagnostics["reuse_existing_draft"]:
            await fill_reply_input(reply_input.locator, request.reply_text)
        filled_text = await read_input_text(reply_input.locator)
        diagnostics["filled_text_matches"] = filled_text == request.reply_text
        if filled_text != request.reply_text:
            result = _result(
                request,
                success=False,
                stage="fill_reply_input",
                status="blocked",
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
                blocking_reasons=["reply_text_mismatch"],
            )
            payload = write_reply_result(request, result, artifacts_dir, started)
            if not dry_run:
                append_reply_history_from_result(history_path, request, result)
            return payload

        if dry_run:
            if not request.keep_filled:
                await clear_reply_input(reply_input.locator)
                diagnostics["dry_run_cleared"] = True
            result = _result(
                request,
                success=True,
                stage="dry_run_complete",
                status="dry_run",
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

        preflight = await preflight_reply_send(
            page,
            request,
            location=location,
            locate_diag=locate_diag,
            reply_action=reply_action,
            reply_input=reply_input,
            input_locator=reply_input.locator,
            history_path=history_path,
            idempotency_key=idempotency_key,
        )
        diagnostics["preflight"] = preflight
        diagnostics["acceptance_preconditions"] = build_acceptance_preconditions(
            request,
            preflight,
            duplicate=None,
            explicit_confirmation=bool(request.confirm_send and (request.yes or request.send_confirmed)),
        )
        if request.acceptance_test:
            print_acceptance_pre_send(request, preflight, idempotency_key, diagnostics["acceptance_preconditions"])
        if preflight.get("already_replied"):
            result = _result(
                request,
                success=False,
                stage="preflight",
                status="duplicate",
                dry_run=False,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                input_found=True,
                text_filled=True,
                already_replied=True,
                preflight=preflight,
                diagnostics=diagnostics,
                error_type="duplicate_reply",
                error="Reply already exists locally or on page",
                blocking_reasons=list(preflight.get("blocking_reasons") or []),
            )
            payload = write_reply_result(request, result, artifacts_dir, started)
            append_reply_history_from_result(history_path, request, result)
            return payload
        if not preflight["ok"]:
            result = _result(
                request,
                success=False,
                stage="preflight",
                status="blocked",
                dry_run=False,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                input_found=True,
                text_filled=True,
                preflight=preflight,
                diagnostics=diagnostics,
                error_type="pre_send_safety_failed",
                error="; ".join(preflight.get("blocking_reasons") or ["preflight failed"]),
                blocking_reasons=list(preflight.get("blocking_reasons") or []),
            )
            payload = write_reply_result(request, result, artifacts_dir, started)
            append_reply_history_from_result(history_path, request, result)
            return payload

        composer = await find_reply_composer(page, reply_input.locator)
        diagnostics["reply_composer_found"] = composer.locator is not None and composer.matched_count == 1
        diagnostics["reply_composer_strategy"] = composer.strategy
        diagnostics["reply_composer_depth"] = composer.depth
        if composer.matched_count != 1 or composer.locator is None:
            result = _result(
                request,
                success=False,
                stage="find_reply_composer",
                status="blocked",
                dry_run=False,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                input_found=True,
                text_filled=True,
                preflight=preflight,
                diagnostics=diagnostics,
                error_type="reply_composer_not_found",
                error="Reply composer was not uniquely found from the reply input",
                blocking_reasons=["reply_composer_not_found"],
            )
            payload = write_reply_result(request, result, artifacts_dir, started)
            append_reply_history_from_result(history_path, request, result)
            return payload

        send_action = await find_send_action(page, reply_input.locator, composer=composer.locator)
        diagnostics["composer_send_action_matched_count"] = send_action.matched_count
        diagnostics["send_action"] = {
            "strategy": send_action.strategy,
            "matched_count": send_action.matched_count,
        }
        if send_action.matched_count != 1 or send_action.locator is None:
            result = _result(
                request,
                success=False,
                stage="find_send_action",
                status="blocked",
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
                blocking_reasons=["send_action_not_unique"],
            )
            payload = write_reply_result(request, result, artifacts_dir, started)
            append_reply_history_from_result(history_path, request, result)
            return payload

        final_precheck = await final_send_precheck(
            request,
            reply_input.locator,
            composer.locator,
            send_action,
        )
        diagnostics["final_send_precheck"] = final_precheck
        if not final_precheck["ok"]:
            result = _result(
                request,
                success=False,
                stage="final_send_precheck",
                status="blocked",
                dry_run=False,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                input_found=True,
                text_filled=True,
                preflight=preflight,
                diagnostics=diagnostics,
                error_type="final_send_precheck_failed",
                error=str(final_precheck.get("reason") or "final send precheck failed"),
                blocking_reasons=[str(final_precheck.get("reason") or "final_send_precheck_failed")],
            )
            payload = write_reply_result(request, result, artifacts_dir, started)
            append_reply_history_from_result(history_path, request, result)
            return payload

        send_action_performed = False
        try:
            await send_action.locator.click(timeout=5000)
            send_action_performed = True
            diagnostics["send_action_count"] = int(diagnostics.get("send_action_count") or 0) + 1
            interim = _result(
                request,
                success=False,
                stage="send_action_performed",
                status="unverified",
                dry_run=False,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                input_found=True,
                text_filled=True,
                sent=False,
                send_action_performed=True,
                verified=False,
                preflight=preflight,
                diagnostics=diagnostics,
                error_type="verification_pending",
                error="Send action was performed; verification has not completed yet",
            )
            write_reply_result(request, interim, artifacts_dir, started)
            append_reply_history_from_result(history_path, request, interim)
        except Exception as exc:
            result = _result(
                request,
                success=False,
                stage="send_action",
                status="send_failed",
                dry_run=False,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                input_found=True,
                text_filled=True,
                preflight=preflight,
                diagnostics=diagnostics,
                error_type=exc.__class__.__name__,
                error=str(exc),
                blocking_reasons=["send_action_failed"],
            )
            payload = write_reply_result(request, result, artifacts_dir, started)
            append_reply_history_from_result(history_path, request, result)
            return payload
        try:
            await page.wait_for_timeout(1500)
        except Exception:
            pass
        verify_started = time.perf_counter()
        try:
            verification = await verify_reply_sent(page, request, reply_input.locator, timeout_seconds=request.verify_timeout_seconds)
        except Exception as exc:
            verification_elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
            result = _result(
                request,
                success=False,
                stage="verification",
                status="unverified",
                dry_run=False,
                located=True,
                locate_strategy=locate_diag.get("strategy"),
                matched_count=matched_count,
                reply_clicked=True,
                input_found=True,
                text_filled=True,
                sent=False,
                send_action_performed=True,
                verified=False,
                verification_strategy="exception",
                verification_elapsed_ms=verification_elapsed_ms,
                preflight=preflight,
                diagnostics=diagnostics,
                error_type=exc.__class__.__name__,
                error=f"Send action was performed but verification failed: {exc}",
            )
            payload = write_reply_result(request, result, artifacts_dir, started)
            append_reply_history_from_result(history_path, request, result)
            return payload
        verification_elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
        diagnostics["verification"] = verification
        verified = bool(verification.get("verified"))
        result = _result(
            request,
            success=verified,
            stage="sent" if verified else "verification",
            status="verified" if verified else "unverified",
            dry_run=False,
            located=True,
            locate_strategy=locate_diag.get("strategy"),
            matched_count=matched_count,
            reply_clicked=True,
            input_found=True,
            text_filled=True,
            sent=verified,
            send_action_performed=send_action_performed,
            verified=verified,
            verification_strategy=verification.get("strategy"),
            verification_elapsed_ms=verification_elapsed_ms,
            preflight=preflight,
            diagnostics=diagnostics,
            error_type=None if verified else "reply_unverified",
            error=None if verified else "Send action was performed but reply was not verified on page",
        )
        payload = write_reply_result(request, result, artifacts_dir, started)
        append_reply_history_from_result(history_path, request, result)
        return payload
    except Exception as exc:
        result = _result(
            request,
            success=False,
            stage="error",
            status="send_failed" if not dry_run else "blocked",
            dry_run=dry_run,
            diagnostics=diagnostics,
            error_type=exc.__class__.__name__,
            error=str(exc),
        )
        payload = write_reply_result(request, result, artifacts_dir, started)
        if not dry_run:
            append_reply_history_from_result(history_path, request, result)
        return payload


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


async def click_reply_action_with_recovery(
    page,
    request: ReplyRequest,
    location,
    locate_diag: dict[str, Any],
    before_snapshot: list[str],
    *,
    max_attempts: int = 2,
) -> ReplyInteractionResult:
    diagnostics: dict[str, Any] = _empty_obstruction_diagnostics()
    diagnostics["page_obstruction_before_reply"] = await detect_page_obstructions(page)
    _merge_obstruction_detection(diagnostics, diagnostics["page_obstruction_before_reply"])
    current_location = location
    current_locate_diag = locate_diag
    last_reply_action = LocatorSearchResult(None, "not_checked", 0)
    last_reply_input = LocatorSearchResult(None, "not_checked", 0)
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        diagnostics["reply_click_attempts"] = attempt
        if attempt > 1:
            current_location = await _locate_for_reply(page, request)
            current_locate_diag = current_location.diagnostics
            diagnostics["locate_after_obstruction_recovery"] = current_locate_diag
            if int(current_locate_diag.get("matched_count") or 0) != 1 or current_location.locator is None:
                return ReplyInteractionResult(
                    current_location,
                    current_locate_diag,
                    last_reply_action,
                    last_reply_input,
                    diagnostics,
                    "comment_not_found_after_obstruction_recovery",
                    "Target comment was not uniquely located after obstruction recovery",
                )

        if attempt > 1:
            existing_input = await find_reply_input(page, current_location.locator, before_snapshot)
            if existing_input.matched_count == 1 and existing_input.locator is not None:
                diagnostics["reply_input_already_present_before_retry"] = True
                diagnostics["reply_click_recovered"] = diagnostics["reply_click_obstructed"]
                diagnostics["reply_input"] = {
                    "strategy": existing_input.strategy,
                    "matched_count": existing_input.matched_count,
                }
                return ReplyInteractionResult(
                    current_location,
                    current_locate_diag,
                    last_reply_action,
                    existing_input,
                    diagnostics,
                )

        reply_action = await find_reply_action(current_location.locator)
        last_reply_action = reply_action
        diagnostics["reply_action"] = {
            "strategy": reply_action.strategy,
            "matched_count": reply_action.matched_count,
        }
        if reply_action.matched_count != 1 or reply_action.locator is None:
            return ReplyInteractionResult(
                current_location,
                current_locate_diag,
                reply_action,
                last_reply_input,
                diagnostics,
                "reply_action_not_unique",
                "Reply action was not uniquely found inside the target comment node",
            )

        try:
            await scroll_locator_into_view(reply_action.locator)
            await reply_action.locator.click(timeout=5000)
            await short_stability_wait(page)
        except Exception as exc:
            last_error = exc
            if not is_pointer_obstruction_error(exc) or attempt >= max_attempts:
                error_type = "reply_action_obstructed" if is_pointer_obstruction_error(exc) else type(exc).__name__
                diagnostics["reply_click_obstructed"] = is_pointer_obstruction_error(exc)
                _merge_obstruction_detection(diagnostics, await detect_page_obstructions(page, target=reply_action.locator))
                return ReplyInteractionResult(
                    current_location,
                    current_locate_diag,
                    reply_action,
                    last_reply_input,
                    diagnostics,
                    error_type,
                    str(exc),
                )
            diagnostics["reply_click_obstructed"] = True
            _merge_obstruction_detection(diagnostics, await detect_page_obstructions(page, target=reply_action.locator))
            diagnostics["obstruction_dismiss_attempted"] = True
            dismiss_result = await dismiss_safe_obstructions(page)
            diagnostics["obstruction_dismissed_count"] += int(dismiss_result.get("dismissed_count") or 0)
            diagnostics.setdefault("obstruction_dismiss_diagnostics", []).append(dismiss_result)
            await short_stability_wait(page)
            continue

        reply_input = await find_reply_input(page, current_location.locator, before_snapshot)
        last_reply_input = reply_input
        diagnostics["reply_input"] = {
            "strategy": reply_input.strategy,
            "matched_count": reply_input.matched_count,
        }
        if reply_input.matched_count == 1 and reply_input.locator is not None:
            diagnostics["reply_click_recovered"] = diagnostics["reply_click_obstructed"]
            return ReplyInteractionResult(
                current_location,
                current_locate_diag,
                reply_action,
                reply_input,
                diagnostics,
            )
        return ReplyInteractionResult(current_location, current_locate_diag, reply_action, reply_input, diagnostics)

    return ReplyInteractionResult(
        current_location,
        current_locate_diag,
        last_reply_action,
        last_reply_input,
        diagnostics,
        "reply_action_obstructed",
        str(last_error) if last_error else "Reply action was obstructed",
    )


def _empty_obstruction_diagnostics() -> dict[str, Any]:
    return {
        "obstruction_detected": False,
        "obstruction_types": [],
        "obstruction_dismiss_attempted": False,
        "obstruction_dismissed_count": 0,
        "reply_click_attempts": 0,
        "reply_click_obstructed": False,
        "reply_click_recovered": False,
    }


def _merge_obstruction_detection(diagnostics: dict[str, Any], detection: dict[str, Any]) -> None:
    if detection.get("obstruction_found"):
        diagnostics["obstruction_detected"] = True
    types = list(diagnostics.get("obstruction_types") or [])
    for obstruction_type in detection.get("obstruction_types") or []:
        if obstruction_type not in types:
            types.append(obstruction_type)
    diagnostics["obstruction_types"] = types
    diagnostics["obstruction_dismissable_count"] = max(
        int(diagnostics.get("obstruction_dismissable_count") or 0),
        int(detection.get("dismissable_count") or 0),
    )


async def detect_page_obstructions(page, *, target=None) -> dict[str, Any]:
    if hasattr(page, "detect_page_obstructions"):
        return dict(await page.detect_page_obstructions(target=target))
    script = """
    (target) => {
      const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
      const result = {obstruction_found: false, obstruction_types: [], dismissable_count: 0, diagnostics: []};
      const add = (type, el) => {
        if (!result.obstruction_types.includes(type)) result.obstruction_types.push(type);
        result.obstruction_found = true;
        result.diagnostics.push({
          type,
          tag: el.tagName,
          role: el.getAttribute('role'),
          ariaLabel: el.getAttribute('aria-label'),
          text: (el.innerText || '').slice(0, 80),
          rect: (() => {
            const rect = el.getBoundingClientRect();
            return {x: rect.x, y: rect.y, width: rect.width, height: rect.height};
          })(),
        });
      };
      const visible = (el) => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
      };
      const dismissText = /^(close|dismiss|not now|稍后|关闭|×|x)$/i;
      document.querySelectorAll('[role="dialog"], [aria-modal="true"]').forEach((el) => {
        if (visible(el)) add('dialog', el);
      });
      document.querySelectorAll('button, [role="button"], [aria-label]').forEach((el) => {
        if (!visible(el)) return;
        const label = (el.getAttribute('aria-label') || el.innerText || '').trim();
        if (dismissText.test(label)) result.dismissable_count += 1;
      });
      document.querySelectorAll('body *').forEach((el) => {
        if (!visible(el)) return;
        const style = getComputedStyle(el);
        if (!['fixed', 'sticky'].includes(style.position)) return;
        const rect = el.getBoundingClientRect();
        const z = Number.parseInt(style.zIndex || '0', 10) || 0;
        if (rect.y <= 90 && rect.height >= 40 && rect.width >= viewportWidth * 0.4 && z >= 1) {
          const role = el.getAttribute('role') || '';
          const label = (el.getAttribute('aria-label') || '').toLowerCase();
          const text = (el.innerText || '').toLowerCase();
          const hasDismiss = Array.from(el.querySelectorAll('button, [role="button"], [aria-label]')).some((child) => {
            const childLabel = (child.getAttribute('aria-label') || child.innerText || '').trim();
            return dismissText.test(childLabel);
          });
          if (role === 'navigation' || role === 'banner') return;
          if (label.includes('notification') || text.includes('notification') || text.includes('通知')) {
            add('notification_drawer', el);
          } else if (rect.height < viewportHeight * 0.6 && hasDismiss) {
            add('top_overlay', el);
          }
        }
      });
      if (target) {
        const rect = target.getBoundingClientRect();
        const x = Math.min(Math.max(rect.left + rect.width / 2, 0), Math.max(viewportWidth - 1, 0));
        const y = Math.min(Math.max(rect.top + rect.height / 2, 0), Math.max(viewportHeight - 1, 0));
        const top = document.elementFromPoint(x, y);
        if (top && top !== target && !target.contains(top)) add('target_covered', top);
      }
      return result;
    }
    """
    try:
        return dict(await page.evaluate(script, target))
    except Exception as exc:
        return {"obstruction_found": False, "obstruction_types": [], "dismissable_count": 0, "diagnostics": [{"error": str(exc)}]}


async def dismiss_safe_obstructions(page, *, max_attempts: int = 3) -> dict[str, Any]:
    if hasattr(page, "dismiss_safe_obstructions"):
        return dict(await page.dismiss_safe_obstructions(max_attempts=max_attempts))
    labels = [re.compile(r"^(Close|Dismiss|Not now|稍后|关闭|X|×)$", re.I)]
    dismissed = 0
    attempts: list[dict[str, Any]] = []
    for _ in range(max_attempts):
        clicked = False
        for label in labels:
            if not hasattr(page, "get_by_role"):
                continue
            locator = cast(Any, page.get_by_role("button", name=label))
            count = await _safe_count(locator)
            attempts.append({"strategy": "safe_button_label", "matched_count": count})
            if 1 <= count <= 3:
                try:
                    first = locator.first
                    if first is None:
                        continue
                    await first.click(timeout=1500)
                    dismissed += 1
                    clicked = True
                    await short_stability_wait(page)
                    break
                except Exception as exc:
                    attempts[-1]["error"] = str(exc)
        if not clicked:
            break
        detection = await detect_page_obstructions(page)
        if not detection.get("obstruction_found"):
            break
    return {"dismissed_count": dismissed, "attempts": attempts}


async def scroll_locator_into_view(locator) -> None:
    if hasattr(locator, "scroll_into_view_if_needed"):
        try:
            await locator.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass


async def short_stability_wait(page, ms: int = 500) -> None:
    try:
        await page.wait_for_timeout(ms)
    except Exception:
        pass


def is_pointer_obstruction_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "intercepts pointer events" in message or "elementfrompoint" in message or "pointer" in message and "intercept" in message


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


async def preflight_reply_send(
    page,
    request: ReplyRequest,
    *,
    location: Any,
    locate_diag: dict[str, Any],
    reply_action: LocatorSearchResult,
    reply_input: LocatorSearchResult,
    input_locator: Any,
    history_path: str | Path,
    idempotency_key: str,
) -> dict[str, Any]:
    blocking_reasons: list[str] = []
    warnings: list[str] = []
    matched_count = int(locate_diag.get("matched_count") or 0)
    lead_found = bool(request.comment_id or request.fingerprint or request.comment_text)
    reply_text_present = bool((request.reply_text or "").strip())
    page_state_valid = True
    already_replied = False

    if not lead_found:
        blocking_reasons.append("lead_identity_missing")
    if matched_count == 0:
        blocking_reasons.append("comment_not_found")
    elif matched_count > 1:
        blocking_reasons.append("comment_not_unique")
    if not reply_text_present:
        blocking_reasons.append("reply_text_empty")
    if reply_action.matched_count != 1 or reply_action.locator is None:
        blocking_reasons.append("reply_action_not_unique")
    if reply_input.matched_count != 1 or reply_input.locator is None:
        blocking_reasons.append("reply_input_not_unique")

    safety = await pre_send_safety_check(page, request, input_locator)
    if not safety.get("ok"):
        page_state_valid = False
        blocking_reasons.append(str(safety.get("reason") or "page_state_invalid"))

    duplicate = find_successful_duplicate(
        history_path,
        comment_id=request.comment_id,
        fingerprint=request.fingerprint,
        idempotency_key=idempotency_key,
        reply_text=request.reply_text,
    )
    if duplicate and not request.allow_duplicate:
        already_replied = True
        blocking_reasons.append("duplicate_history")

    page_duplicate = await page_has_existing_reply(page, location.locator, request.reply_text)
    if page_duplicate and not request.allow_duplicate:
        already_replied = True
        blocking_reasons.append("duplicate_on_page")

    if request.allow_duplicate and (duplicate or page_duplicate):
        warnings.append("duplicate override enabled")

    return {
        "ok": not blocking_reasons,
        "lead_found": lead_found,
        "comment_located": matched_count == 1 and location.locator is not None,
        "matched_count": matched_count,
        "reply_action_found": reply_action.matched_count == 1 and reply_action.locator is not None,
        "reply_input_found": reply_input.matched_count == 1 and reply_input.locator is not None,
        "reply_text_present": reply_text_present,
        "already_replied": already_replied,
        "page_state_valid": page_state_valid,
        "send_allowed": not blocking_reasons,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "locate_strategy": locate_diag.get("strategy"),
        "safety": safety,
    }


async def find_reply_composer(page, input_locator, *, max_depth: int = 8) -> ReplyComposerSearchResult:
    if hasattr(page, "find_reply_composer"):
        return await page.find_reply_composer(input_locator=input_locator, max_depth=max_depth)
    for depth in range(1, max_depth + 1):
        candidate = input_locator.locator(f"xpath=ancestor::*[{depth}]")
        if await _safe_count(candidate) != 1:
            continue
        send_count = await count_scoped_send_candidates(candidate)
        if send_count >= 1:
            return ReplyComposerSearchResult(candidate, "ancestor_scoped", 1, depth)
    return ReplyComposerSearchResult(None, "not_found", 0, None)


async def count_scoped_send_candidates(search_root) -> int:
    result = await find_send_action(None, None, composer=search_root)
    return result.matched_count


async def find_send_action(page, input_locator, *, composer=None) -> LocatorSearchResult:
    if hasattr(page, "find_send_action"):
        try:
            return await page.find_send_action(input_locator=input_locator, composer=composer)
        except TypeError:
            return await page.find_send_action(input_locator)
    if composer is None:
        return LocatorSearchResult(None, "reply_composer_required", 0)
    search_root = composer
    candidates = [
        ("composer_role_send_button", _role_button_locator(search_root, SEND_LABEL_RE)),
        ("composer_aria_send_button", search_root.locator(_send_label_selector())),
        ("composer_button_unambiguous", search_root.locator(_composer_button_selector())),
    ]
    return await _first_unique_locator_without_nth(candidates)


async def final_send_precheck(
    request: ReplyRequest,
    input_locator,
    composer,
    send_action: LocatorSearchResult,
) -> dict[str, Any]:
    input_count = await _safe_count(input_locator)
    composer_count = await _safe_count(composer)
    if input_count != 1:
        return {"ok": False, "reason": "reply_input_not_attached", "reply_input_count": input_count}
    if composer_count != 1:
        return {"ok": False, "reason": "reply_composer_not_attached", "reply_composer_count": composer_count}
    input_visible = await _safe_is_visible(input_locator)
    if not input_visible:
        return {"ok": False, "reason": "reply_input_not_visible"}
    composer_contains_input = await _safe_composer_contains_input(composer, input_locator)
    if not composer_contains_input:
        return {"ok": False, "reason": "reply_composer_missing_input"}
    current_text = await read_input_text(input_locator)
    if current_text != request.reply_text:
        return {"ok": False, "reason": "reply_text_mismatch_before_send", "current_text": current_text}
    if send_action.matched_count != 1 or send_action.locator is None:
        return {"ok": False, "reason": "send_action_not_unique", "send_action_matched_count": send_action.matched_count}
    return {
        "ok": True,
        "reason": None,
        "reply_input_visible": True,
        "reply_composer_attached": True,
        "composer_contains_reply_input": True,
        "send_action_matched_count": send_action.matched_count,
        "reply_text_matches": True,
    }


async def verify_reply_sent(page, request: ReplyRequest, input_locator, timeout_seconds: float = 15.0) -> dict[str, Any]:
    if hasattr(page, "verify_reply_sent"):
        try:
            return await page.verify_reply_sent(request=request, input_locator=input_locator, timeout_seconds=timeout_seconds)
        except TypeError:
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


async def page_has_existing_reply(page, comment_node, reply_text: str | None) -> bool:
    normalized = normalize_reply_text(reply_text)
    if not normalized:
        return False
    if hasattr(page, "page_has_existing_reply"):
        return bool(await page.page_has_existing_reply(comment_node=comment_node, reply_text=reply_text))
    return False


def find_successful_duplicate(
    history_path: str | Path,
    *,
    comment_id: str | None,
    fingerprint: str | None,
    idempotency_key: str | None = None,
    reply_text: str | None = None,
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
        if not (item.get("verified") is True or item.get("status") == "verified" or item.get("success") is True):
            continue
        if idempotency_key and item.get("idempotency_key") == idempotency_key:
            return item
        if comment_id and item.get("comment_id") == comment_id and normalize_reply_text(item.get("reply_text")) == normalize_reply_text(reply_text):
            return item
        if comment_id and item.get("comment_id") == comment_id and reply_text is None:
            return item
        if fingerprint and item.get("fingerprint") == fingerprint and normalize_reply_text(item.get("reply_text")) == normalize_reply_text(reply_text):
            return item
    return None


def find_blocking_reply_history(
    history_path: str | Path,
    *,
    comment_id: str | None,
    fingerprint: str | None,
    idempotency_key: str | None,
    reply_text: str | None,
) -> dict[str, Any] | None:
    path = Path(history_path)
    if not path.exists():
        return None
    unverified: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not _history_item_matches(
            item,
            comment_id=comment_id,
            fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            reply_text=reply_text,
        ):
            continue
        if item.get("verified") is True or item.get("status") == "verified" or item.get("success") is True:
            return {**item, "block_status": "duplicate"}
        if item.get("send_action_performed") is True and item.get("verified") is False:
            unverified = {**item, "block_status": "blocked_unverified_previous_attempt"}
    return unverified


def _history_item_matches(
    item: dict[str, Any],
    *,
    comment_id: str | None,
    fingerprint: str | None,
    idempotency_key: str | None,
    reply_text: str | None,
) -> bool:
    if idempotency_key and item.get("idempotency_key") == idempotency_key:
        return True
    normalized_reply = normalize_reply_text(reply_text)
    if comment_id and item.get("comment_id") == comment_id and normalize_reply_text(item.get("reply_text")) == normalized_reply:
        return True
    if fingerprint and item.get("fingerprint") == fingerprint and normalize_reply_text(item.get("reply_text")) == normalized_reply:
        return True
    return False


def append_reply_history(history_path: str | Path, request: ReplyRequest, *, verified: bool) -> None:
    result = _result(
        request,
        success=verified,
        stage="history_compat",
        status="verified" if verified else "unverified",
        dry_run=False,
        sent=verified,
        verified=verified,
        send_action_performed=verified,
    )
    append_reply_history_from_result(history_path, request, result)


def append_reply_history_from_result(history_path: str | Path, request: ReplyRequest, result: ReplyResult) -> None:
    path = Path(history_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": result.status,
        "success": result.success,
        "author_name": request.author_name,
        "fingerprint": request.fingerprint,
        "comment_id": request.comment_id,
        "comment_url": request.direct_comment_url,
        "source_content_url": request.source_content_url,
        "comment_text": request.comment_text,
        "reply_text": request.reply_text,
        "reply_source": request.reply_source,
        "idempotency_key": result.idempotency_key or build_reply_idempotency_key(request),
        "locate_strategy": result.locate_strategy,
        "matched_count": result.matched_count,
        "preflight_ok": bool(result.preflight.get("ok")) if result.preflight else None,
        "confirm_send": request.confirm_send,
        "confirmed_by_yes": request.yes,
        "confirmed_interactively": request.send_confirmed,
        "send_action_performed": result.send_action_performed,
        "verified": result.verified,
        "sent": result.sent,
        "cancelled": result.cancelled,
        "already_replied": result.already_replied,
        "error_type": result.error_type,
        "error_message": result.error,
    }
    if request.batch_mode or request.plan_id or request.batch_id or request.plan_index is not None:
        entry.update(
            {
                "plan_id": request.plan_id,
                "batch_id": request.batch_id,
                "plan_index": request.plan_index,
                "batch_mode": bool(request.batch_mode),
            }
        )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def build_reply_idempotency_key(request: ReplyRequest) -> str:
    parts = [
        request.source_content_url or "",
        request.comment_id or request.fingerprint or request.direct_comment_url or "",
        normalize_reply_text(request.reply_text),
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def normalize_reply_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _is_ignorable_existing_draft(value: str | None, request: ReplyRequest) -> bool:
    text = " ".join((value or "").split())
    author = " ".join((request.author_name or "").split())
    return bool(text and author and text == author)


def build_acceptance_preconditions(
    request: ReplyRequest,
    preflight: dict[str, Any],
    *,
    duplicate: dict[str, Any] | None,
    explicit_confirmation: bool,
) -> list[dict[str, Any]]:
    return [
        {"name": "Single lead selected", "pass": bool(request.lead_index or request.comment_id or request.direct_comment_url)},
        {"name": "Comment uniquely located", "pass": preflight.get("matched_count") == 1},
        {"name": "Reply text present", "pass": bool((request.reply_text or "").strip())},
        {"name": "No verified local duplicate", "pass": duplicate is None and "duplicate_history" not in preflight.get("blocking_reasons", [])},
        {"name": "No page duplicate", "pass": "duplicate_on_page" not in preflight.get("blocking_reasons", [])},
        {"name": "Preflight passed", "pass": bool(preflight.get("ok"))},
        {"name": "Explicit send confirmation present", "pass": explicit_confirmation},
    ]


def print_acceptance_pre_send(
    request: ReplyRequest,
    preflight: dict[str, Any],
    idempotency_key: str,
    preconditions: list[dict[str, Any]],
) -> None:
    print("=== Phase 4D.1 Acceptance Test ===")
    print(f"Author:\n{request.author_name or ''}")
    print(f"Comment:\n{request.comment_text or ''}")
    print(f"Source content:\n{request.source_content_url}")
    print(f"Direct comment URL:\n{request.direct_comment_url or ''}")
    print("Rule decision:\nsee lead_report")
    print("LLM decision:\nsee lead_report")
    print("LLM confidence:\nsee lead_report")
    print(f"Reply source:\n{request.reply_source}")
    print(f"Final reply:\n{request.reply_text}")
    print(f"Locate strategy:\n{preflight.get('locate_strategy') or ''}")
    print(f"Idempotency key:\n{idempotency_key}")
    print(f"History duplicate:\n{'duplicate_history' in preflight.get('blocking_reasons', [])}")
    print(f"Page duplicate:\n{'duplicate_on_page' in preflight.get('blocking_reasons', [])}")
    print(f"Preflight:\n{'PASS' if preflight.get('ok') else 'FAIL'}")
    print("Acceptance Preconditions")
    for item in preconditions:
        marker = "PASS" if item["pass"] else "FAIL"
        print(f"[{marker}] {item['name']}")
    if all(item["pass"] for item in preconditions):
        print("THIS WILL SEND ONE REAL FACEBOOK REPLY")
    else:
        print("ACCEPTANCE BLOCKED")


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
    reply_source: str = "manual",
    send_confirmed: bool = False,
    preview_only: bool = False,
    verify_timeout_seconds: float = 15.0,
    acceptance_test: bool = False,
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
        resolved_reply_text = (lead.get("llm_review") or {}).get("suggested_reply")
        if not resolved_reply_text:
            raise ValueError("--use-suggested-reply requested but selected lead has no suggested_reply")
        reply_source = "llm_suggested"
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
        reply_source=reply_source,
        send_confirmed=send_confirmed,
        preview_only=preview_only,
        verify_timeout_seconds=verify_timeout_seconds,
        acceptance_test=acceptance_test,
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
    status: str | None = None,
    send_action_performed: bool = False,
    verified: bool = False,
    verification_strategy: str | None = None,
    verification_elapsed_ms: int | None = None,
    already_replied: bool = False,
    cancelled: bool = False,
    blocking_reasons: list[str] | None = None,
    preflight: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
    error_type: str | None = None,
    error: str | None = None,
) -> ReplyResult:
    resolved_status = status or ("dry_run" if dry_run else ("verified" if sent else "blocked"))
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
        status=resolved_status,
        send_action_performed=send_action_performed,
        verified=verified,
        verification_strategy=verification_strategy,
        verification_elapsed_ms=verification_elapsed_ms,
        already_replied=already_replied,
        cancelled=cancelled,
        blocking_reasons=blocking_reasons or [],
        idempotency_key=build_reply_idempotency_key(request),
        reply_source=request.reply_source,
        preflight=preflight or {},
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


async def _first_unique_locator_without_nth(candidates: list[tuple[str, Any]]) -> LocatorSearchResult:
    fallback_multi: LocatorSearchResult | None = None
    for strategy, locator in candidates:
        count = await _safe_count(locator)
        if count == 1:
            return LocatorSearchResult(locator, strategy, count)
        if count > 1 and fallback_multi is None:
            fallback_multi = LocatorSearchResult(None, strategy, count)
    return fallback_multi or LocatorSearchResult(None, "not_found", 0)


async def _safe_count(locator) -> int:
    try:
        return int(await locator.count())
    except Exception:
        return 0


async def _safe_is_visible(locator) -> bool:
    if not hasattr(locator, "is_visible"):
        return await _safe_count(locator) == 1
    try:
        return bool(await locator.is_visible(timeout=1000))
    except TypeError:
        try:
            return bool(await locator.is_visible())
        except Exception:
            return False
    except Exception:
        return False


async def _safe_composer_contains_input(composer, input_locator) -> bool:
    if hasattr(composer, "contains_input"):
        return bool(await composer.contains_input(input_locator))
    return await _safe_count(composer) == 1 and await _safe_count(input_locator) == 1


def _role_button_locator(root, name_pattern: re.Pattern[str]):
    if hasattr(root, "get_by_role"):
        return root.get_by_role("button", name=name_pattern)
    return root.locator("[role='button'], button").filter(has_text=name_pattern)


def _send_label_selector() -> str:
    labels = [
        "Send",
        "Post",
        "Reply",
        "发送",
        "发布",
        "发布评论",
        "发表评论",
        "发送回复",
        "回复",
        "回覆",
    ]
    selectors: list[str] = []
    for label in labels:
        selectors.append(f"[aria-label='{label}']")
        selectors.append(f"[title='{label}']")
    selectors.extend(
        [
            "[aria-label*='send' i]",
            "[aria-label*='post' i]",
            "[aria-label*='reply' i]",
            "[title*='send' i]",
            "[title*='post' i]",
            "[title*='reply' i]",
        ]
    )
    return ", ".join(selectors)


def _composer_button_selector() -> str:
    excluded = [
        "Emoji",
        "GIF",
        "Photo",
        "Sticker",
        "Attach",
        "Camera",
        "Voice",
        "Avatar",
        "表情",
        "图片",
        "视频",
        "动图",
        "贴纸",
        "附件",
        "照片",
        "虚拟形象",
    ]
    exclusions = ""
    for label in excluded:
        if label.isascii():
            exclusions += f":not([aria-label*='{label}' i]):not([title*='{label}' i])"
        else:
            exclusions += f":not([aria-label*='{label}']):not([title*='{label}'])"
    return (
        f"button:not([disabled]){exclusions}, "
        f"[role='button']:not([aria-disabled='true']){exclusions}"
    )


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
