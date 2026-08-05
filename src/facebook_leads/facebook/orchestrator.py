from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from .diagnostics import write_json
from .login_state import detect_login_state
from .report import build_lead_report, write_lead_report_files
from .reply_batch import (
    BatchPlanConfig,
    build_batch_plan,
    enrich_lead_report_missing_reviews,
    resolve_batch_max,
    resolve_daily_limit,
    resolve_interval_seconds,
    write_batch_plan_files,
)
from .target_policy import TargetPolicyConfig, annotate_report_targets, build_target_policy_config, target_policy_from_env
from src.facebook_leads.browser_adapter import (
    BrowserCdpNotConfiguredError,
    get_browser_window_size,
    require_browser_cdp,
    select_active_or_facebook_page,
)


RUN_ROOT = Path("artifacts/facebook_leads/runs")
LOCK_PATH = Path("artifacts/facebook_leads/.orchestrator.lock")
LATEST_RUN_PATH = Path("artifacts/facebook_leads/latest_run.json")
JOB_HISTORY_PATH = Path("artifacts/facebook_leads/job_history.jsonl")
DEFAULT_LOCK_TIMEOUT_MINUTES = 120


@dataclass(frozen=True)
class FacebookLeadsRunConfig:
    cdp_url: str | None = None
    keyword: str | None = None
    max_contents: int = 3
    max_comments: int = 50
    max_scrolls: int = 5
    max_expand_clicks: int = 20
    llm_review: bool = True
    llm_batch_size: int = 10
    llm_model: str | None = None
    llm_concurrency: int | None = None
    llm_timeout_seconds: float | None = None
    llm_max_batch_chars: int | None = None
    max_leads: int = 5
    min_confidence: float = 0.9
    daily_limit: int = 10
    interval_seconds: float = 30.0
    history_path: str = "artifacts/facebook_leads/reply_history.jsonl"
    runs_root: str = str(RUN_ROOT)
    lock_path: str = str(LOCK_PATH)
    latest_run_path: str = str(LATEST_RUN_PATH)
    job_history_path: str = str(JOB_HISTORY_PATH)
    lock_timeout_minutes: int = DEFAULT_LOCK_TIMEOUT_MINUTES
    dry_run: bool = False
    resume_run_id: str | None = None
    target_policy: TargetPolicyConfig = field(default_factory=build_target_policy_config)
    custom_positive_keywords: tuple[str, ...] = ()
    excluded_content_identities: frozenset[str] = frozenset()


@dataclass
class OrchestratorDeps:
    health_check: Callable[[], Awaitable[dict[str, Any]]] | None = None
    scan: Callable[[FacebookLeadsRunConfig, Path], Awaitable[dict[str, Any]]] | None = None
    enrich: Callable[[Path, FacebookLeadsRunConfig, Path], Awaitable[dict[str, Any]]] | None = None
    build_plan: Callable[[Path, FacebookLeadsRunConfig, Path], dict[str, Any]] | None = None
    sleep: Callable[[float], Awaitable[None]] | None = None


async def run_facebook_leads_job(config: FacebookLeadsRunConfig, deps: OrchestratorDeps | None = None) -> dict[str, Any]:
    deps = deps or OrchestratorDeps()
    started = datetime.now(timezone.utc)
    run_id = config.resume_run_id or _new_run_id(started)
    run_dir = Path(config.runs_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "logs" / "run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "job_state.json"
    paths: dict[str, str] = {}
    stale_lock_recovered = False
    previous_run_id = None

    def log(message: str) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {message}\n")

    state = _load_state(state_path) if config.resume_run_id and state_path.exists() else _initial_state(run_id, started)
    state["paths"].setdefault("run_log", str(log_path))
    _write_state(state_path, state, stage="init")

    lock = JobLock(Path(config.lock_path), timeout_minutes=config.lock_timeout_minutes)
    acquired = lock.acquire(run_id)
    stale_lock_recovered = lock.stale_lock_recovered
    previous_run_id = lock.previous_run_id
    if not acquired:
        result = _blocked_result(
            config,
            run_id,
            run_dir,
            started,
            "job_already_running",
            "Another Facebook Leads job is already running",
            stale_lock_recovered=False,
            previous_run_id=lock.previous_run_id,
        )
        result["paths"]["run_log"] = str(log_path)
        _write_state(state_path, result["job_state"], stage="lock")
        _write_final_artifacts(config, result)
        return result

    try:
        _write_state(state_path, state, stage="browser_check")
        health = await _with_retry(lambda: _call_health_check(deps, config), retryable_errors=(BrowserCdpNotConfiguredError, ConnectionError, TimeoutError))
        if health.get("login_state") != "logged_in":
            result = _blocked_result(
                config,
                run_id,
                run_dir,
                started,
                "facebook_not_logged_in",
                f"Facebook login_state={health.get('login_state')}",
                stale_lock_recovered=stale_lock_recovered,
                previous_run_id=previous_run_id,
                health=health,
            )
            _write_state(state_path, result["job_state"], stage="browser_check")
            _write_final_artifacts(config, result)
            return result

        if config.dry_run:
            result = _completed_result(config, run_id, run_dir, started, health, {}, {}, {}, stale_lock_recovered, previous_run_id)
            result["status"] = "completed"
            result["dry_run"] = True
            result["job_state"]["stage"] = "completed"
            result["job_state"]["status"] = "completed"
            _write_final_artifacts(config, result)
            return result

        scan_payload = _read_json_if_exists(state.get("paths", {}).get("scan_result_json"))
        lead_report_path = Path(state.get("paths", {}).get("lead_report_json", "")) if state.get("paths", {}).get("lead_report_json") else None
        existing_scan_status = _scan_status(scan_payload)
        reusable_scan = bool(scan_payload and lead_report_path and lead_report_path.exists() and existing_scan_status == "completed")
        if not reusable_scan:
            _write_state(state_path, state, stage="scan")
            scan_payload = await _with_retry(lambda: _call_scan(deps, config, run_dir), retryable_errors=(ConnectionError, TimeoutError))
            paths.update(scan_payload.get("paths") or {})
            lead_report_path = Path(paths["lead_report_json"])
            state["scan_status"] = _scan_status(scan_payload)
            state["paths"].update(paths)
            _write_state(state_path, state, stage="lead_report")
            if not scan_payload.get("success"):
                raise RuntimeError(scan_payload.get("scan", {}).get("error") or "scan failed")
        else:
            paths.update(state.get("paths") or {})
            log("resume: using existing scan and lead report")
        if lead_report_path is None:
            raise RuntimeError("lead report path is missing")

        enriched: dict[str, Any] = {}
        plan_source_path = lead_report_path
        if config.llm_review:
            enriched_path_value = state.get("paths", {}).get("lead_report_enriched_json")
            enriched_path = Path(enriched_path_value) if enriched_path_value else None
            if not enriched_path or not enriched_path.exists():
                _write_state(state_path, state, stage="llm_review")
                enriched = await _with_retry(lambda: _call_enrich(deps, lead_report_path, config, run_dir), retryable_errors=(ConnectionError, TimeoutError))
                paths.update(enriched.get("paths") or {})
                state["llm_review_status"] = "completed"
                state["paths"].update(paths)
                _write_state(state_path, state, stage="llm_review")
                plan_source_path = Path(paths["lead_report_enriched_json"])
            else:
                plan_source_path = enriched_path
                enriched = {
                    "summary": _read_json_if_exists(run_dir / "lead_report_enriched.json").get("phase5_1_review", {}),
                    "paths": {"lead_report_enriched_json": str(enriched_path), "lead_report_enriched_html": str(run_dir / "lead_report_enriched.html")},
                }
                log("resume: using existing enriched report")
        else:
            state["llm_review_status"] = "disabled"

        _write_state(state_path, state, stage="batch_plan")
        plan_payload = _call_build_plan(deps, plan_source_path, config, run_dir)
        paths.update(plan_payload.get("paths") or {})
        state["plan_status"] = "completed"
        state["paths"].update(paths)

        result = _completed_result(
            config,
            run_id,
            run_dir,
            started,
            health,
            scan_payload,
            enriched,
            plan_payload,
            stale_lock_recovered,
            previous_run_id,
        )
        result["paths"].update(paths)
        result["paths"]["run_log"] = str(log_path)
        result["job_state"]["paths"] = result["paths"]
        _write_state(state_path, result["job_state"], stage="completed")
        _write_final_artifacts(config, result)
        return result
    except Exception as exc:
        result = _failed_result(config, run_id, run_dir, started, exc, stale_lock_recovered, previous_run_id, paths)
        result["paths"]["run_log"] = str(log_path)
        _write_state(state_path, result["job_state"], stage=result["job_state"].get("stage") or "failed")
        _write_final_artifacts(config, result)
        return result
    finally:
        lock.release(run_id)


class JobLock:
    def __init__(self, path: Path, *, timeout_minutes: int) -> None:
        self.path = path
        self.timeout = timedelta(minutes=timeout_minutes)
        self.stale_lock_recovered = False
        self.previous_run_id: str | None = None

    def acquire(self, run_id: str) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            payload = _read_json_if_exists(self.path)
            self.previous_run_id = payload.get("run_id")
            started_at = _parse_datetime(payload.get("started_at"))
            if started_at and datetime.now(timezone.utc) - started_at > self.timeout:
                self.path.unlink(missing_ok=True)
                self.stale_lock_recovered = True
            else:
                return False
        try:
            self.path.write_text(
                json.dumps({"run_id": run_id, "pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()}, indent=2),
                encoding="utf-8",
            )
        except FileExistsError:
            return False
        return True

    def release(self, run_id: str) -> None:
        payload = _read_json_if_exists(self.path)
        if payload.get("run_id") == run_id:
            self.path.unlink(missing_ok=True)


async def default_health_check(*, cdp_url: str | None = None) -> dict[str, Any]:
    cdp_url = require_browser_cdp(cdp_url=cdp_url)
    window_w, window_h = get_browser_window_size()
    from browser_use.browser.browser import BrowserConfig
    from browser_use.browser.context import BrowserContextConfig
    from src.browser.custom_browser import CustomBrowser

    browser = CustomBrowser(
        config=BrowserConfig(
            cdp_url=cdp_url,
            headless=False,
            new_context_config=BrowserContextConfig(window_width=window_w, window_height=window_h),
        )
    )
    context = await browser.new_context(BrowserContextConfig(force_new_context=False, window_width=window_w, window_height=window_h))
    page = await select_active_or_facebook_page(context)
    return {"cdp_url_configured": True, "cdp_reachable": True, "login_state": await detect_login_state(page), "url": getattr(page, "url", None)}


async def default_scan(config: FacebookLeadsRunConfig, run_dir: Path) -> dict[str, Any]:
    from scripts.facebook_readonly_scan import run_cli_scan
    previous_scan_path = run_dir / "scan_result.json"
    previous_scan = _read_json_if_exists(previous_scan_path) if config.resume_run_id else {}

    scan_args = argparse.Namespace(
        keyword=config.keyword or previous_scan.get("keyword"),
        content_limit=config.max_contents,
        comment_limit=config.max_comments,
        max_scrolls=config.max_scrolls,
        max_expand_clicks=config.max_expand_clicks,
        current_page_only=False,
        output=str(run_dir / "scan_result.json"),
        artifacts_dir=str(run_dir / "logs"),
        resume_scan_result=str(previous_scan_path) if config.resume_run_id else None,
        cdp_url=config.cdp_url,
        excluded_content_identities=config.excluded_content_identities,
    )
    scan_payload = await run_cli_scan(scan_args)
    report = build_lead_report(scan_payload, custom_positive_keywords=config.custom_positive_keywords)
    report_paths = write_lead_report_files(report, run_dir)
    lead_report_json = Path(report_paths["lead_report_json"])
    annotated = annotate_report_targets(_read_json_if_exists(lead_report_json), config.target_policy)
    write_json(lead_report_json, annotated)
    return {
        "success": bool(scan_payload.get("success")),
        "status": _scan_status({"scan": scan_payload, "success": scan_payload.get("success")}),
        "scan": scan_payload,
        "lead_report": report.to_dict(),
        "paths": {"scan_result_json": str(run_dir / "scan_result.json"), **report_paths},
    }


async def default_enrich(lead_report_path: Path, config: FacebookLeadsRunConfig, run_dir: Path) -> dict[str, Any]:
    return await enrich_lead_report_missing_reviews(
        lead_report_path,
        output_dir=run_dir,
        history_path=config.history_path,
        batch_size=config.llm_batch_size,
        model_name=config.llm_model,
        concurrency=config.llm_concurrency,
        timeout_seconds=config.llm_timeout_seconds,
        max_batch_chars=config.llm_max_batch_chars,
    )


def default_build_plan(lead_report_path: Path, config: FacebookLeadsRunConfig, run_dir: Path) -> dict[str, Any]:
    plan = build_batch_plan(
        lead_report_path,
        config=BatchPlanConfig(
            max_leads=config.max_leads,
            min_confidence=config.min_confidence,
            daily_limit=config.daily_limit,
            interval_seconds=config.interval_seconds,
            history_path=config.history_path,
            target_policy=config.target_policy,
        ),
    )
    paths = write_batch_plan_files(plan, run_dir)
    return {"plan": plan.to_dict(), "paths": paths}


def build_config_from_env(args: argparse.Namespace, env: dict[str, str] | None = None) -> FacebookLeadsRunConfig:
    env = dict(env or os.environ)
    llm_review = _resolve_bool(getattr(args, "llm_review", None), getattr(args, "no_llm_review", False), env.get("FACEBOOK_LEADS_RUN_LLM_REVIEW", "true"))
    resume_id = getattr(args, "resume", None)
    default_keyword = None if resume_id else "car detailing"
    target_policy = _target_policy_from_args(args, env)
    return FacebookLeadsRunConfig(
        cdp_url=_pick(getattr(args, "cdp_url", None), env.get("FACEBOOK_CDP_URL"), env.get("BROWSER_CDP"), None),
        keyword=_pick(getattr(args, "keyword", None), env.get("FACEBOOK_LEADS_RUN_KEYWORD"), default_keyword),
        max_contents=int(_pick(getattr(args, "max_contents", None), env.get("FACEBOOK_LEADS_RUN_MAX_CONTENTS"), 3)),
        max_comments=int(_pick(getattr(args, "max_comments", None), env.get("FACEBOOK_LEADS_RUN_MAX_COMMENTS"), 50)),
        llm_review=llm_review,
        max_leads=resolve_batch_max(getattr(args, "max_leads", None), env),
        min_confidence=float(_pick(getattr(args, "min_confidence", None), env.get("FACEBOOK_LEADS_REPLY_MIN_CONFIDENCE"), 0.9)),
        daily_limit=resolve_daily_limit(getattr(args, "daily_limit", None), env),
        interval_seconds=resolve_interval_seconds(getattr(args, "interval_seconds", None), env),
        dry_run=bool(getattr(args, "dry_run", False)),
        resume_run_id=resume_id,
        lock_timeout_minutes=int(env.get("FACEBOOK_LEADS_JOB_LOCK_TIMEOUT_MINUTES", DEFAULT_LOCK_TIMEOUT_MINUTES)),
        target_policy=target_policy,
    )


def config_preview(config: FacebookLeadsRunConfig) -> dict[str, Any]:
    return {
        "keyword": config.keyword,
        "max_contents": config.max_contents,
        "max_comments": config.max_comments,
        "llm_enabled": config.llm_review,
        "batch_max": config.max_leads,
        "daily_limit": config.daily_limit,
        "min_confidence": config.min_confidence,
        "target_policy": config.target_policy.to_dict(),
        "send_disabled": True,
    }


def exit_code_for_result(result: dict[str, Any]) -> int:
    return {"completed": 0, "blocked": 2, "partial": 3, "failed": 4}.get(str(result.get("status")), 4)


async def _call_health_check(deps: OrchestratorDeps, config: FacebookLeadsRunConfig) -> dict[str, Any]:
    if deps.health_check:
        return await deps.health_check()
    return await default_health_check(cdp_url=config.cdp_url)


async def _call_scan(deps: OrchestratorDeps, config: FacebookLeadsRunConfig, run_dir: Path) -> dict[str, Any]:
    return await (deps.scan or default_scan)(config, run_dir)


async def _call_enrich(deps: OrchestratorDeps, lead_report_path: Path, config: FacebookLeadsRunConfig, run_dir: Path) -> dict[str, Any]:
    return await (deps.enrich or default_enrich)(lead_report_path, config, run_dir)


def _call_build_plan(deps: OrchestratorDeps, lead_report_path: Path, config: FacebookLeadsRunConfig, run_dir: Path) -> dict[str, Any]:
    return (deps.build_plan or default_build_plan)(lead_report_path, config, run_dir)


async def _with_retry(factory: Callable[[], Awaitable[dict[str, Any]]], *, retryable_errors: tuple[type[BaseException], ...]) -> dict[str, Any]:
    try:
        return await factory()
    except retryable_errors:
        await asyncio.sleep(1)
        return await factory()


def _initial_state(run_id: str, started: datetime) -> dict[str, Any]:
    now = started.isoformat()
    return {
        "run_id": run_id,
        "status": "running",
        "stage": "init",
        "started_at": now,
        "updated_at": now,
        "finished_at": None,
        "scan_status": None,
        "llm_review_status": None,
        "plan_status": None,
        "error_type": None,
        "error_message": None,
        "paths": {},
    }


def _write_state(path: Path, state: dict[str, Any], *, stage: str) -> None:
    state["stage"] = stage
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(path, state)


def _completed_result(
    config: FacebookLeadsRunConfig,
    run_id: str,
    run_dir: Path,
    started: datetime,
    health: dict[str, Any],
    scan_payload: dict[str, Any],
    enriched: dict[str, Any],
    plan_payload: dict[str, Any],
    stale_lock_recovered: bool,
    previous_run_id: str | None,
) -> dict[str, Any]:
    finished = datetime.now(timezone.utc)
    plan = plan_payload.get("plan") or {}
    summary = plan.get("summary") or {}
    scan_report = scan_payload.get("lead_report") or {}
    review = enriched.get("summary") or plan.get("phase5_1_review") or {}
    selected_count = int(summary.get("selected_count") or 0)
    daily_remaining = int(plan.get("daily_remaining") or 0)
    unverified_lock = int(summary.get("unverified_blocked_count") or 0) > 0
    scan_status = _scan_status(scan_payload)
    selected_items = [item for item in plan.get("items") or [] if item.get("selected")]
    selected_reply_allowed = all(item.get("reply_allowed") is True for item in selected_items)
    ready = bool(selected_count > 0 and daily_remaining > 0 and not unverified_lock and selected_reply_allowed)
    paths = {
        "job_state_json": str(run_dir / "job_state.json"),
        "job_report_json": str(run_dir / "job_report.json"),
        "job_report_html": str(run_dir / "job_report.html"),
        **(scan_payload.get("paths") or {}),
        **(enriched.get("paths") or {}),
        **(plan_payload.get("paths") or {}),
    }
    state = _initial_state(run_id, started)
    job_status = "partial" if scan_status == "partial" else "completed"
    state.update(status=job_status, stage=job_status, finished_at=finished.isoformat(), scan_status=scan_status, llm_review_status="completed" if config.llm_review else "disabled", plan_status="completed", paths=paths)
    return {
        "run_id": run_id,
        "status": job_status,
        "stage": job_status,
        "send_disabled": True,
        "dry_run": bool(config.dry_run),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "elapsed_ms": int((finished - started).total_seconds() * 1000),
        "keyword": config.keyword,
        "health": health,
        "scan_summary": {
            "scan_status": scan_status,
            "discovered_contents": _scan_metric(scan_payload, scan_report, "discovered_contents_count", None),
            "scanned_contents": scan_report.get("scanned_content_count", 0),
            "successful_content_count": _scan_metric(scan_payload, scan_report, "content_success_count", "scanned_content_count"),
            "failed_content_count": _scan_metric(scan_payload, scan_report, "content_failure_count", None),
            "skipped_content_count": _scan_metric(scan_payload, scan_report, "content_skipped_count", None),
            "scanned_comments": scan_report.get("scanned_comment_count", 0),
            "lead_candidates": scan_report.get("lead_candidate_count", 0),
        },
        "llm_review_summary": review,
        "batch_plan_summary": summary,
        "daily_remaining": daily_remaining,
        "ready_for_manual_execution": ready,
        "stale_lock_recovered": stale_lock_recovered,
        "previous_run_id": previous_run_id,
        "paths": paths,
        "job_state": state,
    }


def _blocked_result(
    config: FacebookLeadsRunConfig,
    run_id: str,
    run_dir: Path,
    started: datetime,
    error_type: str,
    error_message: str,
    *,
    stale_lock_recovered: bool,
    previous_run_id: str | None,
    health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    finished = datetime.now(timezone.utc)
    paths = {"job_state_json": str(run_dir / "job_state.json"), "job_report_json": str(run_dir / "job_report.json"), "job_report_html": str(run_dir / "job_report.html")}
    state = _initial_state(run_id, started)
    state.update(status="blocked", finished_at=finished.isoformat(), error_type=error_type, error_message=error_message, paths=paths)
    return {
        "run_id": run_id,
        "status": "blocked",
        "stage": "blocked",
        "send_disabled": True,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "elapsed_ms": int((finished - started).total_seconds() * 1000),
        "keyword": config.keyword,
        "health": health or {},
        "error_type": error_type,
        "error_message": error_message,
        "ready_for_manual_execution": False,
        "stale_lock_recovered": stale_lock_recovered,
        "previous_run_id": previous_run_id,
        "paths": paths,
        "job_state": state,
    }


def _failed_result(config: FacebookLeadsRunConfig, run_id: str, run_dir: Path, started: datetime, exc: Exception, stale_lock_recovered: bool, previous_run_id: str | None, paths: dict[str, str]) -> dict[str, Any]:
    finished = datetime.now(timezone.utc)
    paths = {"job_state_json": str(run_dir / "job_state.json"), "job_report_json": str(run_dir / "job_report.json"), "job_report_html": str(run_dir / "job_report.html"), **paths}
    scan_payload = _read_json_if_exists(paths.get("scan_result_json"))
    lead_report = _read_json_if_exists(paths.get("lead_report_json"))
    scan_summary = _summary_from_artifacts(scan_payload, lead_report)
    state = _initial_state(run_id, started)
    state.update(status="failed", stage="failed", finished_at=finished.isoformat(), error_type=exc.__class__.__name__, error_message=str(exc), paths=paths)
    return {
        "run_id": run_id,
        "status": "failed",
        "stage": "failed",
        "send_disabled": True,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "elapsed_ms": int((finished - started).total_seconds() * 1000),
        "keyword": config.keyword,
        "error_type": exc.__class__.__name__,
        "error_message": str(exc),
        "scan_summary": scan_summary,
        "ready_for_manual_execution": False,
        "stale_lock_recovered": stale_lock_recovered,
        "previous_run_id": previous_run_id,
        "paths": paths,
        "job_state": state,
    }


def _write_final_artifacts(config: FacebookLeadsRunConfig, result: dict[str, Any]) -> None:
    paths = result.setdefault("paths", {})
    report_json = Path(paths.get("job_report_json") or Path(config.runs_root) / result["run_id"] / "job_report.json")
    report_html = Path(paths.get("job_report_html") or report_json.with_suffix(".html"))
    paths["job_report_json"] = str(report_json)
    paths["job_report_html"] = str(report_html)
    report_json.parent.mkdir(parents=True, exist_ok=True)
    write_json(report_json, _public_result(result))
    report_html.write_text(render_job_report_html(result), encoding="utf-8")
    latest = {"run_id": result["run_id"], "path": str(report_json.parent), "status": result["status"], "updated_at": datetime.now(timezone.utc).isoformat()}
    write_json(config.latest_run_path, latest)
    _append_job_history(config.job_history_path, result)


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "job_state"}


def _append_job_history(path: str | Path, result: dict[str, Any]) -> None:
    payload = {
        "run_id": result.get("run_id"),
        "status": result.get("status"),
        "started_at": result.get("started_at"),
        "finished_at": result.get("finished_at"),
        "keyword": result.get("keyword"),
        "lead_candidate_count": (result.get("scan_summary") or {}).get("lead_candidates", 0),
        "selected_count": (result.get("batch_plan_summary") or {}).get("selected_count", 0),
        "ready_for_manual_execution": result.get("ready_for_manual_execution", False),
        "error_type": result.get("error_type"),
        "error_message": result.get("error_message"),
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def render_job_report_html(result: dict[str, Any]) -> str:
    paths = result.get("paths") or {}
    scan_summary = result.get("scan_summary") or {}
    scan_payload = _read_json_if_exists(paths.get("scan_result_json"))
    failures = ((scan_payload.get("diagnostics") or {}).get("content_failures") or [])
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>Facebook Leads Phase 6 Job</title>{_style()}</head>
<body><main>
<header><h1>Facebook Leads 自动任务报告</h1><p>本次自动任务只执行扫描、AI 分析和回复计划生成，不会真实发送 Facebook 回复。</p></header>
<section><h2>Job Summary</h2><div class="metrics">
{_metric("Run ID", result.get("run_id"))}
{_metric("任务状态", result.get("status"))}
{_metric("关键词", result.get("keyword"))}
{_metric("开始时间", result.get("started_at"))}
{_metric("结束时间", result.get("finished_at"))}
{_metric("耗时 ms", result.get("elapsed_ms"))}
{_metric("是否可人工执行", result.get("ready_for_manual_execution"))}
{_metric("send_disabled", result.get("send_disabled"))}
</div></section>
<section><h2>扫描摘要</h2><div class="metrics">
{_metric("扫描状态", scan_summary.get("scan_status") or result.get("status"))}
{_metric("发现内容数", scan_summary.get("discovered_contents"))}
{_metric("成功内容数", scan_summary.get("successful_content_count") or scan_summary.get("scanned_contents"))}
{_metric("失败内容数", scan_summary.get("failed_content_count"))}
{_metric("跳过内容数", scan_summary.get("skipped_content_count"))}
{_metric("扫描评论数", scan_summary.get("scanned_comments"))}
{_metric("潜在线索", scan_summary.get("lead_candidates"))}
</div></section>
{_partial_warning_html(scan_summary)}
{_content_failures_html(failures)}
<section><h2>AI 补审摘要</h2><pre>{_e(json.dumps(result.get("llm_review_summary") or {}, indent=2, ensure_ascii=False))}</pre></section>
<section><h2>Batch Plan 摘要</h2><div class="metrics">
{_metric("可发送", (result.get("batch_plan_summary") or {}).get("eligible_count"))}
{_metric("已选择", (result.get("batch_plan_summary") or {}).get("selected_count"))}
{_metric("历史已回复", (result.get("batch_plan_summary") or {}).get("already_replied_count"))}
{_metric("Blocked Leads", (result.get("batch_plan_summary") or {}).get("blocked_count"))}
{_metric("每日剩余额度", result.get("daily_remaining"))}
{_metric("目标策略", (result.get("batch_plan_summary") or {}).get("target_policy"))}
{_metric("自有来源数", (result.get("batch_plan_summary") or {}).get("owned_source_count"))}
{_metric("白名单来源数", (result.get("batch_plan_summary") or {}).get("allowlisted_source_count"))}
{_metric("允许回复 Lead 数", (result.get("batch_plan_summary") or {}).get("reply_allowed_count"))}
{_metric("仅发现不可回复 Lead 数", (result.get("batch_plan_summary") or {}).get("discovery_only_blocked_count"))}
</div></section>
<section><h2>安全摘要</h2><div class="metrics">
{_metric("无人值守真实发送", False)}
{_metric("自动执行 Batch Plan", False)}
{_metric("send_disabled", result.get("send_disabled"))}
{_metric("stale lock recovered", result.get("stale_lock_recovered"))}
</div></section>
<section><h2>Artifact Links</h2>
{_link("打开 Lead Report", paths.get("lead_report_html"))}
{_link("打开 Enriched Report", paths.get("lead_report_enriched_html"))}
{_link("打开 Batch Plan", paths.get("batch_reply_plan_html"))}
{_link("打开 Job JSON", paths.get("job_report_json"))}
</section>
</main></body></html>"""


def _load_state(path: Path) -> dict[str, Any]:
    return _read_json_if_exists(path)


def _read_json_if_exists(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    target = Path(path)
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _new_run_id(now: datetime) -> str:
    return f"run_{now.strftime('%Y%m%d_%H%M%S')}"


def _scan_status(scan_payload: dict[str, Any]) -> str:
    scan = scan_payload.get("scan") if "scan" in scan_payload else scan_payload
    if not scan:
        return "failed"
    status = scan.get("status")
    if status in {"completed", "partial", "failed"}:
        return status
    if scan.get("partial"):
        return "partial"
    return "completed" if scan.get("success") else "failed"


def _scan_metric(scan_payload: dict[str, Any], report: dict[str, Any], key: str, report_key: str | None) -> int:
    scan = scan_payload.get("scan") if "scan" in scan_payload else scan_payload
    if not isinstance(scan, dict):
        scan = {}
    if key in scan:
        return int(scan.get(key) or 0)
    diagnostics = scan.get("diagnostics") or {}
    if key in diagnostics:
        return int(diagnostics.get(key) or 0)
    if report_key:
        return int(report.get(report_key) or 0)
    return 0


def _summary_from_artifacts(scan_payload: dict[str, Any], lead_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "scan_status": _scan_status(scan_payload),
        "discovered_contents": _scan_metric(scan_payload, lead_report, "discovered_contents_count", None),
        "scanned_contents": int(lead_report.get("scanned_content_count") or _scan_metric(scan_payload, lead_report, "content_success_count", None)),
        "successful_content_count": _scan_metric(scan_payload, lead_report, "content_success_count", "scanned_content_count"),
        "failed_content_count": _scan_metric(scan_payload, lead_report, "content_failure_count", None),
        "skipped_content_count": _scan_metric(scan_payload, lead_report, "content_skipped_count", None),
        "scanned_comments": int(lead_report.get("scanned_comment_count") or len(scan_payload.get("comments") or [])),
        "lead_candidates": int(lead_report.get("lead_candidate_count") or 0),
    }


def _partial_warning_html(scan_summary: dict[str, Any]) -> str:
    if (scan_summary.get("scan_status") != "partial") and not int(scan_summary.get("failed_content_count") or 0):
        return ""
    return "<section><h2>部分扫描警告</h2><p>本次扫描存在部分内容失败，计划仅基于成功扫描内容生成。</p></section>"


def _content_failures_html(failures: list[dict[str, Any]]) -> str:
    if not failures:
        return ""
    rows = "\n".join(
        "<tr>"
        f"<td><a href=\"{_e(item.get('url'))}\" target=\"_blank\" rel=\"noopener\">{_e(item.get('url'))}</a></td>"
        f"<td>{_e(item.get('stage') or item.get('failure_stage'))}</td>"
        f"<td>{_e(item.get('error_type'))}</td>"
        f"<td>{_e(item.get('error_message'))}</td>"
        f"<td>{_e(item.get('retry_count'))}</td>"
        "</tr>"
        for item in failures
    )
    return f"<section><h2>失败内容列表</h2><table><thead><tr><th>URL</th><th>stage</th><th>error_type</th><th>error_message</th><th>retry_count</th></tr></thead><tbody>{rows}</tbody></table></section>"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _pick(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _target_policy_from_args(args: argparse.Namespace, env: dict[str, str]) -> TargetPolicyConfig:
    base = target_policy_from_env(env)
    cli_allowed = list(getattr(args, "allow_source_url", None) or [])
    cli_owned = list(getattr(args, "owned_source_id", None) or [])
    return build_target_policy_config(
        tenant_id=getattr(args, "tenant_id", None) or base.tenant_id,
        policy=getattr(args, "target_policy", None) or base.policy,
        owned_source_ids=[*base.owned_source_ids, *cli_owned],
        allowed_source_urls=[*base.allowed_source_urls, *cli_allowed],
    )


def _resolve_bool(cli_enabled: bool | None, cli_disabled: bool, env_value: str) -> bool:
    if cli_disabled:
        return False
    if cli_enabled:
        return True
    return str(env_value).strip().lower() not in {"0", "false", "no", "off"}


def _metric(label: str, value: Any) -> str:
    return f'<article class="metric"><span>{_e(label)}</span><strong>{_e(value)}</strong></article>'


def _link(label: str, path: str | None) -> str:
    if not path:
        return ""
    return f'<p><a href="{_e(path)}">{_e(label)}</a></p>'


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _style() -> str:
    return """<style>
body{font-family:Arial,"Microsoft YaHei",sans-serif;margin:0;background:#f6f7f9;color:#111827}
main{max-width:1120px;margin:0 auto;padding:24px}
header,section{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:18px;margin-bottom:16px}
h1,h2{margin:0 0 12px}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
.metric{border:1px solid #e5e7eb;border-radius:8px;padding:12px;background:#fafafa}
.metric span{display:block;color:#6b7280;font-size:12px}.metric strong{display:block;margin-top:6px;font-size:18px}
pre{white-space:pre-wrap;background:#f3f4f6;border-radius:8px;padding:12px}
a{color:#0f766e;margin-right:14px}
</style>"""
