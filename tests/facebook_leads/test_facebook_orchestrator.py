import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.facebook_leads.facebook.orchestrator import (
    FacebookLeadsRunConfig,
    JobLock,
    OrchestratorDeps,
    build_config_from_env,
    config_preview,
    default_build_plan,
    exit_code_for_result,
    run_facebook_leads_job,
)
from src.facebook_leads.facebook.target_policy import build_target_policy_config


def run_job(config, deps):
    return asyncio.run(run_facebook_leads_job(config, deps))


def config(tmp_path, **overrides):
    values = {
        "keyword": "car detailing",
        "max_contents": 1,
        "max_comments": 20,
        "runs_root": str(tmp_path / "runs"),
        "lock_path": str(tmp_path / ".orchestrator.lock"),
        "latest_run_path": str(tmp_path / "latest_run.json"),
        "job_history_path": str(tmp_path / "job_history.jsonl"),
        "history_path": str(tmp_path / "reply_history.jsonl"),
        "interval_seconds": 0,
    }
    values.update(overrides)
    return FacebookLeadsRunConfig(**values)


async def ok_health():
    return {"cdp_url_configured": True, "cdp_reachable": True, "login_state": "logged_in", "url": "https://facebook.com/reel/1"}


async def logged_out_health():
    return {"cdp_url_configured": True, "cdp_reachable": True, "login_state": "logged_out"}


def fake_lead_report(keyword="car detailing", lead_count=2):
    leads = []
    for idx in range(lead_count):
        num = idx + 1
        leads.append(
            {
                "comment_fingerprint": f"fp{num}",
                "comment_id": f"c{num}",
                "author_name": f"Author {num}",
                "comment_text": f"How much {num}?",
                "source_content_url": "https://www.facebook.com/reel/1",
                "direct_comment_url": f"https://www.facebook.com/reel/1?comment_id=c{num}",
                "intent_level": "high",
                "rule_intent_level": "high",
                "intent_score": 99,
                "llm_review": {
                    "status": "success",
                    "is_lead": True,
                    "should_reply": True,
                    "confidence": 0.99,
                    "suggested_reply": f"Reply {num}",
                },
            }
        )
    return {
        "keyword": keyword,
        "scanned_content_count": 1,
        "scanned_comment_count": 4,
        "lead_candidate_count": lead_count,
        "contents": [
            {
                "source_content_url": "https://www.facebook.com/reel/1",
                "scanned_comment_count": 4,
                "lead_candidate_count": lead_count,
                "leads": leads,
            }
        ],
    }


async def fake_scan(conf, run_dir):
    path = run_dir / "lead_report.json"
    html = run_dir / "lead_report.html"
    scan = run_dir / "scan_result.json"
    report = fake_lead_report(conf.keyword)
    path.write_text(json.dumps(report), encoding="utf-8")
    html.write_text("<html>lead</html>", encoding="utf-8")
    scan.write_text(json.dumps({"success": True}), encoding="utf-8")
    return {
        "success": True,
        "lead_report": report,
        "scan": {"success": True},
        "paths": {"scan_result_json": str(scan), "lead_report_json": str(path), "lead_report_html": str(html)},
    }


async def failing_scan(conf, run_dir):
    raise RuntimeError("scan failed")


async def fake_enrich(lead_report_path, conf, run_dir):
    data = json.loads(Path(lead_report_path).read_text(encoding="utf-8"))
    data["phase5_1_review"] = {
        "enabled": True,
        "requested_count": 2,
        "success_count": 2,
        "fallback_count": 0,
        "elapsed_ms": 10,
        "prompt_tokens": 11,
        "completion_tokens": 12,
        "total_tokens": 23,
    }
    path = run_dir / "lead_report_enriched.json"
    html = run_dir / "lead_report_enriched.html"
    path.write_text(json.dumps(data), encoding="utf-8")
    html.write_text("<html>enriched</html>", encoding="utf-8")
    return {"summary": data["phase5_1_review"], "paths": {"lead_report_enriched_json": str(path), "lead_report_enriched_html": str(html)}}


async def fallback_enrich(lead_report_path, conf, run_dir):
    payload = await fake_enrich(lead_report_path, conf, run_dir)
    payload["summary"]["fallback_count"] = 1
    payload["summary"]["success_count"] = 1
    return payload


def fake_plan(lead_report_path, conf, run_dir, *, selected_count=2, daily_remaining=7, unverified=0):
    path = run_dir / "batch_reply_plan.json"
    html = run_dir / "batch_reply_plan.html"
    plan = {
        "plan_id": "plan_test",
        "daily_remaining": daily_remaining,
        "summary": {
            "total_leads": 2,
            "eligible_count": selected_count,
            "selected_count": selected_count,
            "blocked_count": 2 - selected_count,
            "already_replied_count": 0,
            "unverified_blocked_count": unverified,
        },
        "items": [],
    }
    path.write_text(json.dumps(plan), encoding="utf-8")
    html.write_text("<html>plan</html>", encoding="utf-8")
    return {"plan": plan, "paths": {"batch_reply_plan_json": str(path), "batch_reply_plan_html": str(html)}}


def deps(**overrides):
    values = {"health_check": ok_health, "scan": fake_scan, "enrich": fake_enrich, "build_plan": fake_plan}
    values.update(overrides)
    return OrchestratorDeps(**values)


def test_complete_job_writes_reports_history_latest_and_ready(tmp_path):
    result = run_job(config(tmp_path), deps())

    assert result["status"] == "completed"
    assert result["send_disabled"] is True
    assert result["ready_for_manual_execution"] is True
    assert result["scan_summary"]["scanned_contents"] == 1
    assert result["scan_summary"]["scanned_comments"] == 4
    assert result["scan_summary"]["lead_candidates"] == 2
    assert result["scan_summary"]["scan_status"] == "completed"
    assert Path(result["paths"]["job_report_json"]).exists()
    assert Path(result["paths"]["job_report_html"]).exists()
    assert json.loads((tmp_path / "latest_run.json").read_text())["run_id"] == result["run_id"]
    assert json.loads((tmp_path / "job_history.jsonl").read_text().splitlines()[-1])["ready_for_manual_execution"] is True


def test_lock_blocks_duplicate_job(tmp_path):
    lock_path = tmp_path / ".orchestrator.lock"
    lock_path.write_text(json.dumps({"run_id": "active", "pid": 123, "started_at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")

    result = run_job(config(tmp_path), deps())

    assert result["status"] == "blocked"
    assert result["error_type"] == "job_already_running"
    assert exit_code_for_result(result) == 2


def test_stale_lock_recovered(tmp_path):
    old = datetime.now(timezone.utc) - timedelta(minutes=200)
    (tmp_path / ".orchestrator.lock").write_text(json.dumps({"run_id": "old_run", "pid": 123, "started_at": old.isoformat()}), encoding="utf-8")

    result = run_job(config(tmp_path, lock_timeout_minutes=120), deps())

    assert result["status"] == "completed"
    assert result["stale_lock_recovered"] is True
    assert result["previous_run_id"] == "old_run"


def test_cdp_unreachable_blocks_after_retry(tmp_path):
    calls = {"count": 0}

    async def health():
        calls["count"] += 1
        raise ConnectionError("cdp down")

    result = run_job(config(tmp_path), deps(health_check=health))

    assert calls["count"] == 2
    assert result["status"] == "failed"
    assert result["error_type"] == "ConnectionError"


def test_facebook_not_logged_in_blocks(tmp_path):
    result = run_job(config(tmp_path), deps(health_check=logged_out_health))

    assert result["status"] == "blocked"
    assert result["error_type"] == "facebook_not_logged_in"
    assert result["ready_for_manual_execution"] is False


def test_scan_failure_fails_job(tmp_path):
    result = run_job(config(tmp_path), deps(scan=failing_scan))

    assert result["status"] == "failed"
    assert result["error_type"] == "RuntimeError"


def test_llm_partial_fallback_recorded(tmp_path):
    result = run_job(config(tmp_path), deps(enrich=fallback_enrich))

    assert result["llm_review_summary"]["fallback_count"] == 1
    assert result["status"] == "completed"


async def partial_scan(conf, run_dir):
    path = run_dir / "lead_report.json"
    html = run_dir / "lead_report.html"
    scan = run_dir / "scan_result.json"
    report = fake_lead_report(conf.keyword)
    scan.write_text(
        json.dumps(
            {
                "success": True,
                "status": "partial",
                "partial": True,
                "discovered_contents_count": 2,
                "content_success_count": 1,
                "content_failure_count": 1,
                "content_skipped_count": 1,
                "diagnostics": {
                    "content_failures": [
                        {
                            "url": "https://www.facebook.com/permalink.php?story_fbid=1",
                            "stage": "content_open",
                            "error_type": "TimeoutError",
                            "error_message": "Page.goto timeout",
                            "retry_count": 1,
                            "skipped": True,
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    path.write_text(json.dumps(report), encoding="utf-8")
    html.write_text("<html>lead</html>", encoding="utf-8")
    return {
        "success": True,
        "status": "partial",
        "lead_report": report,
        "scan": json.loads(scan.read_text(encoding="utf-8")),
        "paths": {"scan_result_json": str(scan), "lead_report_json": str(path), "lead_report_html": str(html)},
    }


def test_partial_scan_still_enters_llm_and_batch_plan(tmp_path):
    result = run_job(config(tmp_path), deps(scan=partial_scan))

    assert result["status"] == "partial"
    assert result["llm_review_summary"]["success_count"] == 2
    assert result["batch_plan_summary"]["selected_count"] == 2
    assert result["ready_for_manual_execution"] is True


def test_partial_job_report_contains_scan_warning_and_failure_rows(tmp_path):
    result = run_job(config(tmp_path), deps(scan=partial_scan))
    html = Path(result["paths"]["job_report_html"]).read_text(encoding="utf-8")

    assert "部分扫描警告" in html
    assert "失败内容列表" in html
    assert "Page.goto timeout" in html


def test_selected_count_zero_ready_false(tmp_path):
    result = run_job(config(tmp_path), deps(build_plan=lambda a, b, c: fake_plan(a, b, c, selected_count=0)))

    assert result["batch_plan_summary"]["selected_count"] == 0
    assert result["ready_for_manual_execution"] is False


def test_daily_remaining_zero_ready_false(tmp_path):
    result = run_job(config(tmp_path), deps(build_plan=lambda a, b, c: fake_plan(a, b, c, daily_remaining=0)))

    assert result["daily_remaining"] == 0
    assert result["ready_for_manual_execution"] is False


def test_unverified_lock_ready_false(tmp_path):
    result = run_job(config(tmp_path), deps(build_plan=lambda a, b, c: fake_plan(a, b, c, unverified=1)))

    assert result["ready_for_manual_execution"] is False


def test_job_state_updates_each_stage(tmp_path):
    result = run_job(config(tmp_path), deps())
    state = json.loads(Path(result["paths"]["job_state_json"]).read_text())

    assert state["status"] == "completed"
    assert state["stage"] == "completed"
    assert state["scan_status"] == "completed"
    assert state["llm_review_status"] == "completed"
    assert state["plan_status"] == "completed"


def test_resume_uses_existing_scan_without_repeating(tmp_path):
    first = run_job(config(tmp_path), deps())
    calls = {"scan": 0}

    async def scan(conf, run_dir):
        calls["scan"] += 1
        return await fake_scan(conf, run_dir)

    second = run_job(config(tmp_path, resume_run_id=first["run_id"]), deps(scan=scan))

    assert second["status"] == "completed"
    assert calls["scan"] == 0


def test_dry_run_does_not_scan(tmp_path):
    async def scan(conf, run_dir):
        raise AssertionError("dry-run must not scan")

    result = run_job(config(tmp_path, dry_run=True), deps(scan=scan))

    assert result["status"] == "completed"
    assert result["dry_run"] is True
    assert result["send_disabled"] is True


def test_print_config_does_not_expose_secret():
    args = argparse.Namespace(
        keyword=None,
        max_contents=None,
        max_comments=None,
        llm_review=None,
        no_llm_review=False,
        max_leads=None,
        min_confidence=None,
        daily_limit=None,
        interval_seconds=None,
        dry_run=False,
        resume=None,
    )
    conf = build_config_from_env(args, {"FACEBOOK_LEADS_RUN_KEYWORD": "cars", "OPENAI_API_KEY": "secret", "FACEBOOK_LEADS_RUN_LLM_REVIEW": "true"})
    preview = json.dumps(config_preview(conf))

    assert "secret" not in preview
    assert "OPENAI_API_KEY" not in preview
    assert '"send_disabled": true' in preview


def test_resume_without_keyword_does_not_default_to_car_detailing():
    args = argparse.Namespace(
        keyword=None,
        max_contents=None,
        max_comments=None,
        llm_review=None,
        no_llm_review=False,
        max_leads=None,
        min_confidence=None,
        daily_limit=None,
        interval_seconds=None,
        dry_run=False,
        resume="run_1",
    )

    conf = build_config_from_env(args, {})

    assert conf.resume_run_id == "run_1"
    assert conf.keyword is None


def test_cli_cdp_explicit_value_precedes_environment_fallback():
    args = argparse.Namespace(
        cdp_url="http://127.0.0.1:9400",
        keyword=None,
        max_contents=None,
        max_comments=None,
        llm_review=None,
        no_llm_review=False,
        max_leads=None,
        min_confidence=None,
        daily_limit=None,
        interval_seconds=None,
        dry_run=True,
        resume=None,
    )

    explicit = build_config_from_env(args, {"FACEBOOK_CDP_URL": "http://127.0.0.1:9222"})
    args.cdp_url = None
    fallback = build_config_from_env(args, {"FACEBOOK_CDP_URL": "http://127.0.0.1:9223"})

    assert explicit.cdp_url == "http://127.0.0.1:9400"
    assert fallback.cdp_url == "http://127.0.0.1:9223"


def test_artifacts_do_not_contain_secret(tmp_path):
    result = run_job(config(tmp_path), deps())
    combined = Path(result["paths"]["job_report_json"]).read_text(encoding="utf-8") + Path(result["paths"]["job_report_html"]).read_text(encoding="utf-8")

    assert "OPENAI_API_KEY" not in combined
    assert "Authorization" not in combined
    assert "Cookie" not in combined


def test_orchestrator_source_does_not_execute_real_send():
    source = Path("src/facebook_leads/facebook/orchestrator.py").read_text(encoding="utf-8")

    assert "confirm_send=True" not in source
    assert "execute=True" not in source
    assert "SEND BATCH" not in source


def test_default_build_plan_generates_selected_count(tmp_path):
    report_path = tmp_path / "lead_report_enriched.json"
    report_path.write_text(json.dumps(fake_lead_report()), encoding="utf-8")

    payload = default_build_plan(
        report_path,
        config(tmp_path, max_leads=1, target_policy=build_target_policy_config(policy="allowlist", allowed_source_urls=["https://www.facebook.com/reel/1"])),
        tmp_path,
    )

    assert payload["plan"]["summary"]["selected_count"] == 1
    assert Path(payload["paths"]["batch_reply_plan_json"]).exists()


def test_job_report_html_contains_required_sections(tmp_path):
    result = run_job(config(tmp_path), deps())
    html = Path(result["paths"]["job_report_html"]).read_text(encoding="utf-8")

    for text in ["Job Summary", "扫描摘要", "AI 补审摘要", "Batch Plan 摘要", "安全摘要", "Artifact Links"]:
        assert text in html


def test_exit_codes():
    assert exit_code_for_result({"status": "completed"}) == 0
    assert exit_code_for_result({"status": "blocked"}) == 2
    assert exit_code_for_result({"status": "partial"}) == 3
    assert exit_code_for_result({"status": "failed"}) == 4


def test_job_lock_release(tmp_path):
    lock = JobLock(tmp_path / "lock.json", timeout_minutes=120)

    assert lock.acquire("run1") is True
    lock.release("run1")
    assert not (tmp_path / "lock.json").exists()
