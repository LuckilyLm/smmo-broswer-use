import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.facebook_reply_batch import run_reply_batch
from src.facebook_leads.facebook.reply_batch import (
    BatchExecuteConfig,
    BatchPlanConfig,
    build_batch_plan,
    build_batch_acceptance_preconditions,
    collect_missing_review_decisions,
    count_today_verified_replies,
    enrich_lead_report_missing_reviews,
    execute_batch_plan,
    resolve_acceptance_max,
    resolve_batch_max,
    resolve_daily_limit,
    resolve_interval_seconds,
    select_acceptance_subset,
    write_batch_plan_files,
    write_batch_result_files,
)
from src.facebook_leads.facebook.llm_models import LLMLeadReview
from src.facebook_leads.facebook.llm_review import _reviewed_lead
from src.facebook_leads.facebook.target_policy import build_target_policy_config


TEST_SOURCE_URL = "https://www.facebook.com/reel/1"


def lead(
    idx,
    *,
    confidence=0.99,
    status="success",
    is_lead=True,
    should_reply=True,
    reply=None,
    comment_id=None,
    intent_level="high",
):
    return {
        "comment_fingerprint": f"fp{idx}",
        "comment_id": comment_id or f"c{idx}",
        "author_name": f"Author {idx}",
        "comment_text": f"How much {idx}?",
        "direct_comment_url": f"{TEST_SOURCE_URL}?comment_id=c{idx}",
        "source_content_url": TEST_SOURCE_URL,
        "intent_level": intent_level,
        "rule_intent_level": intent_level,
        "intent_score": 100 - idx,
        "final_is_lead": True,
        "final_intent_level": intent_level,
        "llm_review": {
            "status": status,
            "is_lead": is_lead,
            "should_reply": should_reply,
            "confidence": confidence,
            "suggested_reply": reply if reply is not None else f"Reply {idx}",
        },
    }


def report_path(tmp_path, leads):
    path = tmp_path / "lead_report.json"
    path.write_text(
        json.dumps({"contents": [{"source_content_url": TEST_SOURCE_URL, "leads": leads}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def write_history(path, *items):
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in items) + "\n", encoding="utf-8")


def verified_history(comment_id, reply_text="Reply 1", *, ts="2026-07-22T00:00:00+00:00"):
    return {
        "timestamp": ts,
        "status": "verified",
        "success": True,
        "verified": True,
        "sent": True,
        "comment_id": comment_id,
        "reply_text": reply_text,
    }


def unverified_history(comment_id, reply_text="Reply 1"):
    return {
        "timestamp": "2026-07-22T00:00:00+00:00",
        "status": "unverified",
        "verified": False,
        "send_action_performed": True,
        "comment_id": comment_id,
        "reply_text": reply_text,
    }


def result_payload(status="verified", *, sent=True, verified=True, send_count=1, error_type=None, blocking=None):
    return {
        "result": {
            "status": status,
            "sent": sent,
            "verified": verified,
            "send_action_performed": send_count > 0,
            "verification_strategy": "fake" if verified else None,
            "verification_elapsed_ms": 1 if verified else None,
            "blocking_reasons": blocking or [],
            "error_type": error_type,
            "error": None,
            "preflight": {"ok": True},
        },
        "diagnostics": {"send_action_count": send_count},
        "paths": {"reply_result_json": f"reply-{status}.json"},
    }


def preflight_payload(*, ok=True, matched_count=1, input_found=True, blocking=None, diagnostics=None):
    return {
        "result": {
            "status": "dry_run" if ok else "blocked",
            "stage": "dry_run_complete" if ok else "locate_comment",
            "located": matched_count == 1,
            "locate_strategy": "comment_id_text",
            "matched_count": matched_count,
            "reply_clicked": matched_count == 1,
            "input_found": input_found,
            "reply_text": "Preview reply",
            "sent": False,
            "verified": False,
            "send_action_performed": False,
            "blocking_reasons": blocking or [],
            "error_type": None if ok else "comment_not_found",
            "error": None if ok else "Target comment was not uniquely located",
            "preflight": {"ok": ok, "matched_count": matched_count, "locate_strategy": "comment_id_text"},
        },
        "diagnostics": {"send_action_count": 0} | (diagnostics or {}),
        "paths": {"reply_result_json": "reply-preflight.json"},
    }


def make_plan(tmp_path, leads=None, **config_overrides):
    history_path = config_overrides.pop("history_path", tmp_path / "history.jsonl")
    config_overrides.setdefault("target_policy", build_target_policy_config(policy="allowlist", allowed_source_urls=[TEST_SOURCE_URL]))
    config = BatchPlanConfig(history_path=history_path, **config_overrides)
    return build_batch_plan(report_path(tmp_path, leads or [lead(1), lead(2)]), config=config)


def allowlist_policy():
    return build_target_policy_config(policy="allowlist", allowed_source_urls=[TEST_SOURCE_URL])


def run_batch(plan, config, runner, **kwargs):
    return asyncio.run(execute_batch_plan(plan.to_dict() if hasattr(plan, "to_dict") else plan, config=config, reply_runner=runner, sleep=kwargs.get("sleep")))


def test_plan_only_does_not_connect_browser_or_send(monkeypatch, tmp_path):
    called = {"browser": False}

    async def fail_browser():
        called["browser"] = True
        raise AssertionError("browser should not be opened")

    monkeypatch.setattr("scripts.facebook_reply_batch.get_active_facebook_page", fail_browser)
    args = type(
        "Args",
        (),
        {
            "lead_report": str(report_path(tmp_path, [lead(1)])),
            "plan_only": True,
            "plan": None,
            "max_leads": 5,
            "daily_limit": 10,
            "interval_seconds": 0,
            "min_confidence": 0.9,
            "history_path": str(tmp_path / "history.jsonl"),
            "output_dir": str(tmp_path),
        },
    )()

    payload = asyncio.run(run_reply_batch(args))

    assert payload["mode"] == "plan_only"
    assert called["browser"] is False
    assert Path(payload["paths"]["batch_reply_plan_json"]).exists()


def test_plan_selects_only_eligible_leads_and_respects_confidence_and_max(tmp_path):
    plan = make_plan(
        tmp_path,
        [lead(1), lead(2, confidence=0.8), lead(3, should_reply=False), lead(4)],
        max_leads=1,
        min_confidence=0.9,
    )

    assert plan.summary["eligible_count"] == 2
    assert plan.summary["selected_count"] == 1
    assert sum(1 for item in plan.items if item["selected"]) == 1
    by_comment = {item["comment_id"]: item for item in plan.items}
    assert "confidence_below_threshold" in by_comment["c2"]["blocking_reasons"]
    assert "llm_should_reply_false" in by_comment["c3"]["blocking_reasons"]


def test_batch_plan_blocks_high_confidence_when_source_not_allowed(tmp_path):
    plan = build_batch_plan(
        report_path(tmp_path, [lead(1, confidence=0.99)]),
        config=BatchPlanConfig(history_path=tmp_path / "history.jsonl"),
    )

    assert plan.summary["eligible_count"] == 0
    assert plan.summary["selected_count"] == 0
    assert plan.items[0]["reply_allowed"] is False
    assert "source_not_allowed" in plan.items[0]["blocking_reasons"]


def test_batch_plan_allows_high_confidence_when_source_allowed(tmp_path):
    plan = make_plan(tmp_path, [lead(1, confidence=0.99)])

    assert plan.summary["eligible_count"] == 1
    assert plan.summary["selected_count"] == 1
    assert plan.items[0]["reply_allowed"] is True


def test_plan_excludes_verified_duplicate_and_unverified_previous_attempt(tmp_path):
    history = tmp_path / "history.jsonl"
    write_history(history, verified_history("c1"), unverified_history("c2", "Reply 2"))

    plan = make_plan(tmp_path, [lead(1), lead(2), lead(3)], history_path=history)

    assert "duplicate_history" in plan.items[0]["blocking_reasons"]
    assert "unverified_previous_attempt" in plan.items[1]["blocking_reasons"]
    assert plan.summary["already_replied_count"] == 1
    assert plan.summary["unverified_blocked_count"] == 1
    assert plan.items[2]["selected"] is True


def test_env_resolvers_precedence():
    env = {
        "FACEBOOK_LEADS_REPLY_BATCH_MAX": "3",
        "FACEBOOK_LEADS_REPLY_DAILY_LIMIT": "7",
        "FACEBOOK_LEADS_REPLY_INTERVAL_SECONDS": "2.5",
    }

    assert resolve_batch_max(None, env) == 3
    assert resolve_batch_max(4, env) == 4
    assert resolve_daily_limit(None, env) == 7
    assert resolve_interval_seconds(None, env) == 2.5


def test_daily_limit_counts_only_today_verified(tmp_path):
    history = tmp_path / "history.jsonl"
    write_history(
        history,
        verified_history("c1", ts="2026-07-22T00:00:00+00:00"),
        {**verified_history("c2", ts="2026-07-21T00:00:00+00:00")},
        {"timestamp": "2026-07-22T00:00:00+00:00", "status": "blocked", "verified": False, "sent": False},
    )

    assert count_today_verified_replies(history, now=datetime(2026, 7, 22, tzinfo=timezone.utc)) == 1


def test_execute_without_confirm_send_never_calls_runner(tmp_path):
    plan = make_plan(tmp_path)
    called = {"count": 0}

    async def runner(page, request):
        called["count"] += 1
        return result_payload()

    result = run_batch(plan, BatchExecuteConfig(execute=True, confirm_send=False, confirmed=False, interval_seconds=0), runner)

    assert result["status"] == "cancelled"
    assert called["count"] == 0


def test_execute_blocks_forged_plan_item_when_reply_not_allowed(tmp_path):
    plan = make_plan(tmp_path, [lead(1)])
    plan_dict = plan.to_dict()
    plan_dict["items"][0]["reply_allowed"] = False
    plan_dict["items"][0]["ownership_status"] = "third_party"
    plan_dict["items"][0]["blocking_reasons"] = []
    plan_dict["items"][0]["eligible"] = True
    plan_dict["items"][0]["selected"] = True

    async def runner(page, request):
        raise AssertionError("source guard should block before runner")

    result = run_batch(plan_dict, BatchExecuteConfig(execute=True, confirm_send=True, confirmed=True, interval_seconds=0), runner)

    assert result["attempted_count"] == 1
    assert result["results"][0]["blocking_reasons"] == ["source_not_allowed"]
    assert result["results"][0]["send_action_count"] == 0


def test_execute_wrong_confirmation_cancelled(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.facebook_reply_batch.confirm_batch_interactive", lambda: False)
    monkeypatch.setattr("scripts.facebook_reply_batch.get_active_facebook_page", lambda: None)
    plan = make_plan(tmp_path)
    plan_path = tmp_path / "batch_reply_plan.json"
    plan_path.write_text(json.dumps(plan.to_dict(), ensure_ascii=False), encoding="utf-8")
    args = _execute_args(plan_path, tmp_path, execute=True, confirm_send=True, yes_batch=False)

    payload = asyncio.run(run_reply_batch(args))

    assert payload["result"]["status"] == "cancelled"


def test_send_batch_confirmation_accepts_exact_piped_stdin(monkeypatch):
    class FakePipe:
        def isatty(self):
            return False

        def read(self):
            return "SEND BATCH\n"

    monkeypatch.setattr("scripts.facebook_reply_batch.sys.stdin", FakePipe())

    from scripts.facebook_reply_batch import confirm_batch_interactive

    assert confirm_batch_interactive() is True


def test_send_batch_confirmation_rejects_wrong_piped_stdin(monkeypatch):
    class FakePipe:
        def isatty(self):
            return False

        def read(self):
            return "SEND ALL\n"

    monkeypatch.setattr("scripts.facebook_reply_batch.sys.stdin", FakePipe())

    from scripts.facebook_reply_batch import confirm_batch_interactive

    assert confirm_batch_interactive() is False


def test_send_batch_confirmation_allows_start(tmp_path):
    plan = make_plan(tmp_path)
    calls = []

    async def runner(page, request):
        calls.append(request)
        return result_payload()

    result = run_batch(plan, BatchExecuteConfig(execute=True, confirm_send=True, confirmed=True, interval_seconds=0), runner)

    assert result["attempted_count"] == 2
    assert result["verified_count"] == 2
    assert all(req.confirm_send and req.yes and req.batch_mode for req in calls)


@pytest.mark.parametrize(
    "status,sent,verified,error_type,blocking,expected_status",
    [
        ("duplicate", False, False, None, ["duplicate_history"], "partial"),
        ("blocked", False, False, None, ["comment_not_found"], "partial"),
        ("send_failed", False, False, "RuntimeError", ["send_action_failed"], "partial"),
    ],
)
def test_duplicate_blocked_and_send_failed_continue(tmp_path, status, sent, verified, error_type, blocking, expected_status):
    plan = make_plan(tmp_path, [lead(1), lead(2)])
    responses = [
        result_payload(status, sent=sent, verified=verified, send_count=0, error_type=error_type, blocking=blocking),
        result_payload("verified"),
    ]

    async def runner(page, request):
        return responses.pop(0)

    result = run_batch(plan, BatchExecuteConfig(execute=True, confirm_send=True, confirmed=True, interval_seconds=0), runner)

    assert result["status"] == expected_status
    assert result["attempted_count"] == 2
    assert result["verified_count"] == 1


def test_unverified_stops_and_does_not_process_later_leads(tmp_path):
    plan = make_plan(tmp_path, [lead(1), lead(2), lead(3)])
    calls = []

    async def runner(page, request):
        calls.append(request.plan_index)
        return result_payload("unverified", sent=False, verified=False, send_count=1)

    result = run_batch(plan, BatchExecuteConfig(execute=True, confirm_send=True, confirmed=True, interval_seconds=0), runner)

    assert result["status"] == "stopped_unverified"
    assert calls == [1]


def test_login_lost_and_browser_disconnected_stop_batch(tmp_path):
    plan = make_plan(tmp_path, [lead(1), lead(2)])

    async def login_runner(page, request):
        return result_payload("blocked", sent=False, verified=False, send_count=0, blocking=["login state blocks send: logged_out"])

    class BrowserDisconnectedError(Exception):
        pass

    async def browser_runner(page, request):
        raise BrowserDisconnectedError("gone")

    assert run_batch(plan, BatchExecuteConfig(execute=True, confirm_send=True, confirmed=True, interval_seconds=0), login_runner)["status"] == "stopped_login"
    assert run_batch(plan, BatchExecuteConfig(execute=True, confirm_send=True, confirmed=True, interval_seconds=0), browser_runner)["status"] == "stopped_browser"


def test_daily_limit_stops_execution(tmp_path):
    history = tmp_path / "history.jsonl"
    write_history(history, verified_history("old"))
    plan = make_plan(tmp_path, [lead(1), lead(2)], history_path=history, daily_limit=1)
    called = {"count": 0}

    async def runner(page, request):
        called["count"] += 1
        return result_payload()

    result = run_batch(plan, BatchExecuteConfig(execute=True, confirm_send=True, confirmed=True, daily_limit=1, history_path=history), runner)

    assert result["status"] == "daily_limit_reached"
    assert called["count"] == 0


def test_interval_seconds_is_used_between_real_sends(tmp_path):
    plan = make_plan(tmp_path, [lead(1), lead(2)])
    sleeps = []

    async def runner(page, request):
        return result_payload()

    async def sleep(seconds):
        sleeps.append(seconds)

    result = run_batch(plan, BatchExecuteConfig(execute=True, confirm_send=True, confirmed=True, interval_seconds=3), runner, sleep=sleep)

    assert result["verified_count"] == 2
    assert sleeps == [3]


def test_result_json_html_and_plan_html_are_written(tmp_path):
    plan = make_plan(tmp_path)
    plan_paths = write_batch_plan_files(plan, tmp_path)
    result = {
        "batch_id": "batch_1",
        "status": "completed",
        "planned_count": 1,
        "attempted_count": 1,
        "verified_count": 1,
        "duplicate_count": 0,
        "blocked_count": 0,
        "failed_count": 0,
        "unverified_count": 0,
        "started_at": "now",
        "finished_at": "later",
        "results": [result_payload()["result"] | {"plan_index": 1, "reply_text": "Hi"}],
    }
    result_paths = write_batch_result_files(result, tmp_path)

    assert Path(plan_paths["batch_reply_plan_json"]).exists()
    plan_html = Path(plan_paths["batch_reply_plan_html"]).read_text(encoding="utf-8")
    report_html = Path(result_paths["batch_reply_report_html"]).read_text(encoding="utf-8")
    assert "Facebook 批量回复计划" in plan_html
    assert "复制建议回复" in plan_html
    assert "Facebook 批量回复执行报告" in report_html
    assert "真实发送成功" in report_html


def test_batch_history_fields_are_added_by_request(tmp_path):
    plan = make_plan(tmp_path, [lead(1)])
    captured = []

    async def runner(page, request):
        captured.append(request)
        return result_payload()

    result = run_batch(plan, BatchExecuteConfig(execute=True, confirm_send=True, confirmed=True, interval_seconds=0), runner)

    assert result["verified_count"] == 1
    assert captured[0].plan_id == plan.plan_id
    assert captured[0].batch_id.startswith("batch_")
    assert captured[0].plan_index == 1
    assert captured[0].batch_mode is True


def test_single_cli_source_still_requires_yes_for_real_send():
    source = Path("scripts/facebook_reply_one.py").read_text(encoding="utf-8")

    assert "--yes" in source
    assert "Type SEND to confirm" in source


def test_phase5_1_missing_review_detection_skips_existing_success_and_verified(tmp_path):
    history = tmp_path / "history.jsonl"
    write_history(history, verified_history("c4", "old reply"))
    leads = [
        lead(1, status="success"),
        lead(2, status=None),
        lead(3, status="failed"),
        lead(4, status=None),
        lead(5, status="timeout"),
    ]
    report = json.loads(report_path(tmp_path, leads).read_text(encoding="utf-8"))

    decisions = collect_missing_review_decisions(report, history_path=history)

    assert [item["action"] for item in decisions] == ["existing", "review", "review", "skip_verified", "review"]
    assert [item.get("attempt_source") for item in decisions if item["action"] == "review"] == [
        "phase5_1_missing_review",
        "phase5_1_retry_failed",
        "phase5_1_retry_timeout",
    ]


def test_phase5_1_enriches_missing_reviews_preserves_order_and_original(tmp_path, monkeypatch):
    report = report_path(tmp_path, [lead(1), lead(2, status=None), lead(3, status="failed")])
    original_text = report.read_text(encoding="utf-8")
    requested = []

    async def fake_review(leads, **kwargs):
        requested.extend(leads)
        reviewed = [
            _reviewed_lead(
                leads[0],
                LLMLeadReview(
                    comment_fingerprint=leads[0].comment_fingerprint,
                    status="success",
                    is_lead=True,
                    confidence=0.96,
                    intent_level="high",
                    intent_types=["price"],
                    reason_zh="用户明确询价。",
                    summary_zh="询价",
                    suggested_reply="Hi, please DM us for the latest price.",
                    should_reply=True,
                ),
            ),
            _reviewed_lead(
                leads[1],
                LLMLeadReview(
                    comment_fingerprint=leads[1].comment_fingerprint,
                    status="failed",
                    is_lead=False,
                    confidence=0.0,
                    intent_level="none",
                    error="fake failure",
                ),
            ),
        ]
        return {
            "reviewed": reviewed,
            "summary": {
                "success_count": 1,
                "fallback_count": 1,
                "model": "fake-model",
                "prompt_version": "phase4c2-v1",
                "call_count": 1,
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            },
        }

    monkeypatch.setattr("src.facebook_leads.facebook.reply_batch.review_leads_with_llm_detailed", fake_review)

    payload = asyncio.run(
        enrich_lead_report_missing_reviews(
            report,
            output_dir=tmp_path / "phase5_1",
            history_path=tmp_path / "history.jsonl",
        )
    )

    enriched_path = Path(payload["paths"]["lead_report_enriched_json"])
    enriched = json.loads(enriched_path.read_text(encoding="utf-8"))
    enriched_leads = enriched["contents"][0]["leads"]
    assert report.read_text(encoding="utf-8") == original_text
    assert [item["comment_id"] for item in enriched_leads] == ["c1", "c2", "c3"]
    assert [lead.comment_fingerprint for lead in requested] == ["fp2", "fp3"]
    assert enriched_leads[0]["llm_review_source"] == "existing"
    assert enriched_leads[1]["llm_review_source"] == "phase5_1_reviewed"
    assert enriched_leads[2]["llm_review_source"] == "phase5_1_fallback"
    assert enriched["phase5_1_review"]["existing_success_count"] == 1
    assert enriched["phase5_1_review"]["missing_llm_review_count"] == 2
    assert enriched["phase5_1_review"]["requested_count"] == 2
    assert enriched["phase5_1_review"]["success_count"] == 1
    assert enriched["phase5_1_review"]["fallback_count"] == 1
    assert enriched["phase5_1_review"]["model"] == "fake-model"
    assert enriched["phase5_1_review"]["total_tokens"] == 30
    assert Path(payload["paths"]["lead_report_enriched_html"]).exists()


def test_phase5_1_regenerated_plan_uses_review_sources_and_blocks_failed(tmp_path, monkeypatch):
    source = report_path(tmp_path, [lead(1, status=None), lead(2, status="failed")])

    async def fake_review(leads, **kwargs):
        return {
            "reviewed": [
                _reviewed_lead(
                    leads[0],
                    LLMLeadReview(
                        comment_fingerprint=leads[0].comment_fingerprint,
                        status="success",
                        is_lead=True,
                        confidence=0.95,
                        intent_level="high",
                        suggested_reply="Hi, please DM us for details.",
                        should_reply=True,
                    ),
                ),
                _reviewed_lead(
                    leads[1],
                    LLMLeadReview(
                        comment_fingerprint=leads[1].comment_fingerprint,
                        status="success",
                        is_lead=False,
                        confidence=0.30,
                        intent_level="none",
                        should_reply=False,
                    ),
                ),
            ],
            "summary": {"success_count": 2, "fallback_count": 0, "call_count": 1},
        }

    monkeypatch.setattr("src.facebook_leads.facebook.reply_batch.review_leads_with_llm_detailed", fake_review)
    enriched = asyncio.run(enrich_lead_report_missing_reviews(source, output_dir=tmp_path / "phase5_1", history_path=tmp_path / "history.jsonl"))

    plan = build_batch_plan(
        enriched["paths"]["lead_report_enriched_json"],
        config=BatchPlanConfig(max_leads=5, min_confidence=0.9, history_path=tmp_path / "history.jsonl", target_policy=allowlist_policy()),
    )

    assert plan.summary["eligible_count"] == 1
    assert plan.summary["selected_count"] == 1
    assert plan.items[0]["llm_review_source"] == "phase5_1_reviewed"
    assert plan.items[0]["eligible"] is True
    assert plan.items[1]["llm_review_source"] == "phase5_1_reviewed"
    assert {"llm_not_lead", "llm_should_reply_false", "confidence_below_threshold"} <= set(plan.items[1]["blocking_reasons"])


def test_phase5_1_verified_duplicate_is_excluded_from_plan_after_enrichment(tmp_path):
    history = tmp_path / "history.jsonl"
    write_history(history, verified_history("c1", "previous"))
    source = report_path(tmp_path, [lead(1, status=None)])

    payload = asyncio.run(
        enrich_lead_report_missing_reviews(
            source,
            output_dir=tmp_path / "phase5_1",
            history_path=history,
            dry_run=True,
        )
    )
    plan = build_batch_plan(
        payload["paths"]["lead_report_enriched_json"],
        config=BatchPlanConfig(max_leads=5, min_confidence=0.9, history_path=history, target_policy=allowlist_policy()),
    )

    enriched = payload["lead_report"]["contents"][0]["leads"][0]
    assert enriched["llm_review_source"] == "not_reviewed"
    assert enriched["review_attempt_source"] == "already_verified_reply"
    assert "llm_review_not_success" in plan.items[0]["blocking_reasons"]
    assert "duplicate_history" in plan.items[0]["blocking_reasons"]
    assert plan.summary["selected_count"] == 0


def test_phase5_1_cli_review_missing_plan_only_does_not_open_browser_or_modify_history(tmp_path, monkeypatch):
    history = tmp_path / "history.jsonl"
    history.write_text("", encoding="utf-8")
    source = report_path(tmp_path, [lead(1, status=None)])
    called = {"browser": False, "review": False}

    async def fail_browser():
        called["browser"] = True
        raise AssertionError("browser should not be opened")

    async def fake_review(leads, **kwargs):
        called["review"] = True
        return {
            "reviewed": [
                _reviewed_lead(
                    leads[0],
                    LLMLeadReview(
                        comment_fingerprint=leads[0].comment_fingerprint,
                        status="success",
                        is_lead=True,
                        confidence=0.99,
                        intent_level="high",
                        suggested_reply="Hi, please DM us.",
                        should_reply=True,
                    ),
                )
            ],
            "summary": {"success_count": 1, "fallback_count": 0, "call_count": 1, "model": "fake-model"},
        }

    monkeypatch.setattr("scripts.facebook_reply_batch.get_active_facebook_page", fail_browser)
    monkeypatch.setattr("src.facebook_leads.facebook.reply_batch.review_leads_with_llm_detailed", fake_review)
    args = _plan_args(source, tmp_path, history_path=history, review_missing=True)

    payload = asyncio.run(run_reply_batch(args))

    assert payload["mode"] == "review_missing_plan_only"
    assert called == {"browser": False, "review": True}
    assert history.read_text(encoding="utf-8") == ""
    assert Path(payload["paths"]["lead_report_enriched_json"]).exists()
    assert Path(payload["paths"]["batch_reply_plan_json"]).exists()
    assert payload["plan"]["summary"]["selected_count"] == 1


def test_phase5_1_html_contains_review_summary_and_chinese_blocking_reasons(tmp_path, monkeypatch):
    source = report_path(tmp_path, [lead(1, confidence=0.1, status="failed", reply="")])
    payload = asyncio.run(
        enrich_lead_report_missing_reviews(
            source,
            output_dir=tmp_path / "phase5_1",
            history_path=tmp_path / "history.jsonl",
            dry_run=True,
        )
    )
    plan = build_batch_plan(
        payload["paths"]["lead_report_enriched_json"],
        config=BatchPlanConfig(max_leads=5, min_confidence=0.9, history_path=tmp_path / "history.jsonl", target_policy=allowlist_policy()),
    )
    paths = write_batch_plan_files(plan, tmp_path / "phase5_1")

    enriched_html = Path(payload["paths"]["lead_report_enriched_html"]).read_text(encoding="utf-8")
    plan_html = Path(paths["batch_reply_plan_html"]).read_text(encoding="utf-8")
    assert "AI 补审摘要" in enriched_html
    assert "AI 补审摘要" in plan_html
    assert "AI 复核未成功" in plan_html
    assert "AI 置信度低于阈值" in plan_html
    assert "Phase 5.1" in plan_html


def test_phase5_1_max_leads_and_daily_remaining_still_apply(tmp_path, monkeypatch):
    history = tmp_path / "history.jsonl"
    write_history(history, verified_history("old"))
    source = report_path(tmp_path, [lead(1, status=None), lead(2, status=None), lead(3, status=None)])

    async def fake_review(leads, **kwargs):
        return {
            "reviewed": [
                _reviewed_lead(
                    item,
                    LLMLeadReview(
                        comment_fingerprint=item.comment_fingerprint,
                        status="success",
                        is_lead=True,
                        confidence=0.99,
                        intent_level="high",
                        suggested_reply=f"Reply for {item.comment_fingerprint}",
                        should_reply=True,
                    ),
                )
                for item in leads
            ],
            "summary": {"success_count": 3, "fallback_count": 0, "call_count": 1},
        }

    monkeypatch.setattr("src.facebook_leads.facebook.reply_batch.review_leads_with_llm_detailed", fake_review)
    enriched = asyncio.run(enrich_lead_report_missing_reviews(source, output_dir=tmp_path / "phase5_1", history_path=history))

    plan = build_batch_plan(
        enriched["paths"]["lead_report_enriched_json"],
        config=BatchPlanConfig(max_leads=5, daily_limit=2, min_confidence=0.9, history_path=history, target_policy=allowlist_policy()),
    )

    assert plan.summary["eligible_count"] == 3
    assert plan.daily_remaining == 1
    assert plan.summary["selected_count"] == 1


def test_acceptance_max_defaults_env_and_rejects_above_two():
    assert resolve_acceptance_max(None, {}) == 2
    assert resolve_acceptance_max(1, {}) == 1
    assert resolve_acceptance_max(None, {"FACEBOOK_LEADS_REPLY_ACCEPTANCE_MAX": "2"}) == 2
    with pytest.raises(ValueError):
        resolve_acceptance_max(3, {})


def test_acceptance_subset_uses_first_two_selected_and_does_not_modify_plan(tmp_path):
    plan = make_plan(tmp_path, [lead(1), lead(2), lead(3), lead(4), lead(5)], max_leads=5)
    before = json.loads(json.dumps(plan.to_dict()))

    subset = select_acceptance_subset(plan.to_dict(), acceptance_max=2)

    assert [item["plan_index"] for item in subset] == [1, 2]
    assert plan.to_dict()["items"] == before["items"]


def test_acceptance_preconditions_block_execute_without_confirm_or_human_confirmation(tmp_path):
    plan = make_plan(tmp_path, [lead(1), lead(2)], max_leads=2).to_dict()
    plan_path = tmp_path / "batch_reply_plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    preconditions = build_batch_acceptance_preconditions(
        plan_path,
        plan,
        acceptance_test=True,
        acceptance_max=2,
        daily_limit=10,
        history_path=tmp_path / "history.jsonl",
        execute=True,
        confirm_send=False,
        confirmed=False,
    )

    by_name = {item["name"]: item["pass"] for item in preconditions}
    assert by_name["Plan loaded"] is True
    assert by_name["Acceptance subset <= 2"] is True
    assert by_name["Confirm-send flag present"] is False
    assert by_name["Human confirmation present"] is False


def test_acceptance_test_alone_review_mode_does_not_open_browser_or_send(monkeypatch, tmp_path):
    called = {"browser": False}

    async def fail_browser():
        called["browser"] = True
        raise AssertionError("browser should not be opened")

    monkeypatch.setattr("scripts.facebook_reply_batch.get_active_facebook_page", fail_browser)
    plan = make_plan(tmp_path, [lead(1), lead(2)], max_leads=2)
    plan_path = tmp_path / "batch_reply_plan.json"
    plan_path.write_text(json.dumps(plan.to_dict(), ensure_ascii=False), encoding="utf-8")

    payload = asyncio.run(run_reply_batch(_execute_args(plan_path, tmp_path, acceptance_test=True)))

    assert payload["mode"] == "plan_review"
    assert called["browser"] is False


def test_acceptance_preflight_only_processes_two_without_send_and_writes_report(tmp_path):
    plan = make_plan(tmp_path, [lead(1), lead(2), lead(3)], max_leads=3)
    calls = []

    async def runner(page, request):
        calls.append(request)
        return result_payload("blocked", sent=False, verified=False, send_count=0, blocking=["preflight_only"])

    result = run_batch(
        plan,
        BatchExecuteConfig(preflight_only=True, acceptance_test=True, acceptance_max=2, interval_seconds=0),
        runner,
    )

    assert [req.plan_index for req in calls] == [1, 2]
    assert all(not req.confirm_send and not req.yes and req.acceptance_test for req in calls)
    assert result["acceptance_test"] is True
    assert result["acceptance_subset_count"] == 2
    assert result["acceptance_subset_plan_indexes"] == [1, 2]
    assert result["attempted_count"] == 2
    assert result["total_send_action_count"] == 0


@pytest.mark.parametrize("status,sent,verified,send_count,expected_status", [
    ("verified", True, True, 1, "completed"),
    ("duplicate", False, False, 0, "partial"),
    ("blocked", False, False, 0, "partial"),
    ("send_failed", False, False, 0, "partial"),
])
def test_acceptance_statuses_continue_to_next_item(tmp_path, status, sent, verified, send_count, expected_status):
    plan = make_plan(tmp_path, [lead(1), lead(2)], max_leads=2)
    responses = [
        result_payload(status, sent=sent, verified=verified, send_count=send_count, blocking=[status] if status != "verified" else []),
        result_payload("verified"),
    ]

    async def runner(page, request):
        return responses.pop(0)

    result = run_batch(
        plan,
        BatchExecuteConfig(execute=True, confirm_send=True, confirmed=True, acceptance_test=True, acceptance_max=2, interval_seconds=0),
        runner,
    )

    assert result["attempted_count"] == 2
    assert result["status"] == expected_status
    assert result["total_send_action_count"] <= 2
    assert all(item["send_action_count"] <= 1 for item in result["results"])


def test_acceptance_unverified_stops_and_does_not_process_later_items(tmp_path):
    plan = make_plan(tmp_path, [lead(1), lead(2), lead(3)], max_leads=3)
    calls = []

    async def runner(page, request):
        calls.append(request.plan_index)
        return result_payload("unverified", sent=False, verified=False, send_count=1)

    result = run_batch(
        plan,
        BatchExecuteConfig(execute=True, confirm_send=True, confirmed=True, acceptance_test=True, acceptance_max=2, interval_seconds=0),
        runner,
    )

    assert result["status"] == "stopped_unverified"
    assert calls == [1]
    assert result["batch_safety"]["unverified_occurred"] is True
    assert result["batch_safety"]["batch_breaker_triggered"] is True


def test_acceptance_browser_login_and_send_action_breakers(tmp_path):
    plan = make_plan(tmp_path, [lead(1), lead(2)], max_leads=2)

    class BrowserDisconnectedError(Exception):
        pass

    async def browser_runner(page, request):
        raise BrowserDisconnectedError("gone")

    async def login_runner(page, request):
        return result_payload("blocked", sent=False, verified=False, send_count=0, blocking=["login state blocks send: logged_out"])

    async def double_send_runner(page, request):
        return result_payload("verified", sent=True, verified=True, send_count=2)

    config = BatchExecuteConfig(execute=True, confirm_send=True, confirmed=True, acceptance_test=True, acceptance_max=2, interval_seconds=0)
    assert run_batch(plan, config, browser_runner)["status"] == "stopped_browser"
    assert run_batch(plan, config, login_runner)["status"] == "stopped_login"
    double = run_batch(plan, config, double_send_runner)
    assert double["status"] == "failed"
    assert double["total_send_action_count"] == 2


def test_acceptance_persists_running_and_after_each_item_before_crash(tmp_path):
    plan = make_plan(tmp_path, [lead(1), lead(2)], max_leads=2)
    snapshots = []

    async def runner(page, request):
        if request.plan_index == 2:
            raise RuntimeError("crash")
        return result_payload("verified")

    def persist(payload):
        path = tmp_path / "persisted.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        snapshots.append(json.loads(path.read_text(encoding="utf-8")))

    result = asyncio.run(
        execute_batch_plan(
            plan,
            config=BatchExecuteConfig(execute=True, confirm_send=True, confirmed=True, acceptance_test=True, acceptance_max=2, interval_seconds=0),
            reply_runner=runner,
            persist=persist,
        )
    )

    assert snapshots[0]["status"] == "running"
    assert any(snapshot["attempted_count"] == 1 and len(snapshot["results"]) == 1 for snapshot in snapshots)
    assert result["attempted_count"] == 2
    assert len(result["results"]) == 2


def test_batch_report_html_contains_acceptance_safety_composer_and_verification(tmp_path):
    result = {
        "batch_id": "batch_1",
        "plan_id": "plan_1",
        "status": "stopped_unverified",
        "acceptance_test": True,
        "acceptance_max": 2,
        "plan_selected_count": 5,
        "acceptance_subset_count": 2,
        "attempted_count": 1,
        "verified_count": 0,
        "duplicate_count": 0,
        "blocked_count": 0,
        "failed_count": 0,
        "send_failed_count": 0,
        "unverified_count": 1,
        "daily_verified_before": 1,
        "daily_verified_after": 1,
        "daily_limit": 10,
        "total_send_action_count": 1,
        "elapsed_ms": 123,
        "interval_seconds": 0,
        "started_at": "start",
        "finished_at": "finish",
        "batch_safety": {"unverified_occurred": True, "batch_breaker_triggered": True, "total_send_action_count": 1, "verified_count": 0},
        "results": [
            {
                "plan_index": 2,
                "author_name": "Chris",
                "comment_text": "Price?",
                "reply_text": "DM us",
                "llm_confidence": 0.99,
                "llm_reason_zh": "询价",
                "status": "unverified",
                "stage": "verification",
                "preflight": {"ok": True},
                "locate_strategy": "comment_id",
                "matched_count": 1,
                "reply_composer_found": True,
                "reply_composer_strategy": "scoped",
                "composer_send_action_matched_count": 1,
                "obstruction_detected": True,
                "obstruction_types": ["top_overlay"],
                "obstruction_dismiss_attempted": True,
                "obstruction_dismissed_count": 1,
                "reply_click_attempts": 2,
                "reply_click_recovered": True,
                "send_action_performed": True,
                "send_action_count": 1,
                "sent": False,
                "verified": False,
                "verification_strategy": "text",
                "verification_elapsed_ms": 1000,
                "blocking_reasons": ["unverified"],
                "source_content_url": "https://www.facebook.com/reel/1",
                "direct_comment_url": "https://www.facebook.com/reel/1?comment_id=1",
                "reply_result_path": "reply.json",
            }
        ],
    }
    paths = write_batch_result_files(result, tmp_path)
    html = Path(paths["batch_reply_report_html"]).read_text(encoding="utf-8")

    assert "Phase 5.2 Acceptance 执行摘要" in html
    assert "Batch Safety Summary" in html
    assert "Reply Composer" in html
    assert "Page Obstruction" in html
    assert "top_overlay" in html
    assert "Recovered" in html
    assert "Verification" in html
    assert "打开原帖" in html
    assert "查看原评论" in html


def test_phase5_1_verified_history_count_keeps_old_verified_skipped_semantics(tmp_path):
    history = tmp_path / "history.jsonl"
    write_history(history, verified_history("c1", "Reply 1"), verified_history("c3", "old reply"))
    source = report_path(tmp_path, [lead(1, status="success"), lead(2, status=None), lead(3, status=None)])

    payload = asyncio.run(
        enrich_lead_report_missing_reviews(
            source,
            output_dir=tmp_path / "phase5_1",
            history_path=history,
            dry_run=True,
        )
    )

    summary = payload["summary"]
    assert summary["verified_history_count"] == 2
    assert summary["verified_skipped_from_review_count"] == 1
    assert summary["verified_skipped_count"] == 1
    assert summary["existing_success_count"] == 1


def test_phase5_2_1_preflight_only_success_maps_to_preflight_passed(tmp_path):
    plan = make_plan(tmp_path, [lead(1)], max_leads=1)

    async def runner(page, request):
        return preflight_payload(ok=True)

    result = run_batch(
        plan,
        BatchExecuteConfig(preflight_only=True, acceptance_test=True, acceptance_max=2),
        runner,
    )

    item = result["results"][0]
    assert result["execution_mode"] == "preflight_only"
    assert item["status"] == "preflight_passed"
    assert item["preflight_ok"] is True
    assert item["send_action_performed"] is False
    assert item["send_action_count"] == 0
    assert item["sent"] is False
    assert item["verified"] is False


def test_phase5_3_1_obstruction_diagnostics_are_summarized(tmp_path):
    plan = make_plan(tmp_path, [lead(1)], max_leads=1)

    async def runner(page, request):
        return preflight_payload(
            ok=True,
            diagnostics={
                "obstruction_detected": True,
                "obstruction_types": ["notification_drawer"],
                "obstruction_dismiss_attempted": True,
                "obstruction_dismissed_count": 1,
                "reply_click_attempts": 2,
                "reply_click_obstructed": True,
                "reply_click_recovered": True,
            },
        )

    result = run_batch(
        plan,
        BatchExecuteConfig(preflight_only=True, acceptance_test=True, acceptance_max=2),
        runner,
    )

    item = result["results"][0]
    assert item["status"] == "preflight_passed"
    assert item["obstruction_detected"] is True
    assert item["obstruction_types"] == ["notification_drawer"]
    assert item["obstruction_dismiss_attempted"] is True
    assert item["obstruction_dismissed_count"] == 1
    assert item["reply_click_attempts"] == 2
    assert item["reply_click_obstructed"] is True
    assert item["reply_click_recovered"] is True


def test_phase5_2_1_preflight_only_failure_maps_to_preflight_failed(tmp_path):
    plan = make_plan(tmp_path, [lead(1)], max_leads=1)

    async def runner(page, request):
        return preflight_payload(ok=False, matched_count=0, input_found=False, blocking=["comment_not_found"])

    result = run_batch(
        plan,
        BatchExecuteConfig(preflight_only=True, acceptance_test=True, acceptance_max=2),
        runner,
    )

    item = result["results"][0]
    assert item["status"] == "preflight_failed"
    assert item["preflight_ok"] is False
    assert result["preflight_passed_count"] == 0
    assert result["preflight_failed_count"] == 1


def test_phase5_2_1_html_uses_preflight_ok_and_shows_na_for_preflight_mode(tmp_path):
    result = {
        "batch_id": "batch_1",
        "plan_id": "plan_1",
        "status": "preflight_only",
        "execution_mode": "preflight_only",
        "acceptance_test": True,
        "acceptance_max": 2,
        "plan_selected_count": 2,
        "acceptance_subset_count": 2,
        "attempted_count": 2,
        "verified_count": 0,
        "duplicate_count": 0,
        "blocked_count": 0,
        "failed_count": 0,
        "send_failed_count": 0,
        "unverified_count": 0,
        "preflight_passed_count": 1,
        "preflight_failed_count": 1,
        "ready_for_real_batch_acceptance": False,
        "daily_verified_before": 1,
        "daily_verified_after": 1,
        "daily_limit": 10,
        "total_send_action_count": 0,
        "elapsed_ms": 123,
        "interval_seconds": 0,
        "started_at": "start",
        "finished_at": "finish",
        "batch_safety": {},
        "results": [
            {
                "plan_index": 2,
                "author_name": "Chris",
                "comment_text": "Price?",
                "reply_text": "DM",
                "status": "preflight_passed",
                "execution_mode": "preflight_only",
                "stage": "dry_run_complete",
                "preflight_ok": True,
                "locate_strategy": "comment_id_text",
                "matched_count": 1,
                "reply_composer_found": True,
                "reply_composer_strategy": "not_checked_in_preflight",
                "composer_send_action_matched_count": "not_checked",
                "send_action_performed": False,
                "send_action_count": 0,
                "sent": False,
                "verified": False,
                "send_action_checked": False,
            },
            {
                "plan_index": 3,
                "author_name": "Ivy",
                "comment_text": "Where?",
                "reply_text": "DM",
                "status": "preflight_failed",
                "execution_mode": "preflight_only",
                "stage": "locate_comment",
                "preflight_ok": False,
                "locate_strategy": "not_found",
                "matched_count": 0,
                "reply_composer_found": False,
                "reply_composer_strategy": "not_checked_in_preflight",
                "composer_send_action_matched_count": "not_checked",
                "send_action_performed": False,
                "send_action_count": 0,
                "sent": False,
                "verified": False,
                "send_action_checked": False,
            },
        ],
    }

    html = Path(write_batch_result_files(result, tmp_path)["batch_reply_report_html"]).read_text(encoding="utf-8")

    assert "Preflight Passed" in html
    assert "Preflight Failed" in html
    assert "Preflight：PASS" in html
    assert "Preflight：FAIL" in html
    assert "Send：Not attempted" in html
    assert "Verification：N/A" in html
    assert "not_checked_in_preflight" in html
    assert "not_checked" in html


def test_phase5_2_1_readiness_true_only_when_all_acceptance_preflight_passes(tmp_path):
    plan = make_plan(tmp_path, [lead(1), lead(2)], max_leads=2)

    async def runner(page, request):
        return preflight_payload(ok=True)

    result = run_batch(
        plan,
        BatchExecuteConfig(preflight_only=True, acceptance_test=True, acceptance_max=2, daily_limit=10),
        runner,
    )

    assert result["preflight_passed_count"] == 2
    assert result["preflight_failed_count"] == 0
    assert result["ready_for_real_batch_acceptance"] is True


def test_phase5_2_1_readiness_false_on_any_preflight_fail(tmp_path):
    plan = make_plan(tmp_path, [lead(1), lead(2)], max_leads=2)
    responses = [preflight_payload(ok=True), preflight_payload(ok=False, matched_count=0, input_found=False)]

    async def runner(page, request):
        return responses.pop(0)

    result = run_batch(
        plan,
        BatchExecuteConfig(preflight_only=True, acceptance_test=True, acceptance_max=2, daily_limit=10),
        runner,
    )

    assert result["preflight_passed_count"] == 1
    assert result["preflight_failed_count"] == 1
    assert result["ready_for_real_batch_acceptance"] is False


def test_phase5_2_1_readiness_false_on_unverified_lock(tmp_path):
    plan = make_plan(tmp_path, [lead(1), lead(2)], max_leads=2)
    plan_dict = plan.to_dict()
    plan_dict["items"][0]["blocking_reasons"].append("unverified_previous_attempt")

    async def runner(page, request):
        return preflight_payload(ok=True)

    result = run_batch(
        plan_dict,
        BatchExecuteConfig(preflight_only=True, acceptance_test=True, acceptance_max=2, daily_limit=10),
        runner,
    )

    assert result["batch_unverified_lock"] is True
    assert result["ready_for_real_batch_acceptance"] is False


def test_preflight_only_marks_verified_history_duplicate_without_browser(tmp_path):
    history = tmp_path / "history.jsonl"
    write_history(history, verified_history("c1", "Reply 1"))
    plan = make_plan(tmp_path, [lead(1, comment_id="c1")], max_leads=1, history_path=tmp_path / "plan_history.jsonl")

    async def runner(page, request):
        raise AssertionError("duplicate preflight should not open browser")

    result = run_batch(
        plan,
        BatchExecuteConfig(preflight_only=True, acceptance_test=True, acceptance_max=1, daily_limit=10, history_path=history),
        runner,
    )

    assert result["status"] == "preflight_only"
    assert result["attempted_count"] == 1
    assert result["duplicate_count"] == 1
    assert result["total_send_action_count"] == 0
    assert result["ready_for_real_batch_acceptance"] is False
    assert result["results"][0]["status"] == "duplicate"
    assert result["results"][0]["send_action_performed"] is False
    assert result["results"][0]["send_action_count"] == 0
    assert result["results"][0]["blocking_reasons"] == ["duplicate_history"]


def test_phase5_2_1_readiness_false_when_daily_remaining_zero(tmp_path):
    history = tmp_path / "history.jsonl"
    write_history(history, verified_history("old"))
    plan = make_plan(tmp_path, [lead(1), lead(2)], max_leads=2, history_path=history)

    async def runner(page, request):
        return preflight_payload(ok=True)

    result = run_batch(
        plan,
        BatchExecuteConfig(preflight_only=True, acceptance_test=True, acceptance_max=2, daily_limit=1, history_path=history),
        runner,
    )

    assert result["status"] == "daily_limit_reached"
    assert result["ready_for_real_batch_acceptance"] is False


def _plan_args(lead_report, tmp_path, *, history_path=None, review_missing=False):
    return type(
        "Args",
        (),
        {
            "lead_report": str(lead_report),
            "plan_only": True,
            "review_missing": review_missing,
            "review_missing_only": False,
            "review_missing_dry_run": False,
            "plan": None,
            "execute": False,
            "dry_run": False,
            "preflight_only": False,
            "confirm_send": False,
            "yes_batch": False,
            "max_leads": 5,
            "daily_limit": 10,
            "interval_seconds": 0,
            "min_confidence": 0.9,
            "history_path": str(history_path or tmp_path / "history.jsonl"),
            "output_dir": str(tmp_path / "phase5_1"),
            "single_artifacts_dir": str(tmp_path / "replies"),
            "llm_batch_size": 10,
            "llm_model": None,
            "llm_concurrency": None,
            "llm_timeout_seconds": None,
            "llm_max_batch_chars": None,
            "target_policy": "allowlist",
            "allow_source_url": [TEST_SOURCE_URL],
            "owned_source_id": [],
            "tenant_id": None,
        },
    )()


def _execute_args(plan_path, tmp_path, *, execute=False, confirm_send=False, yes_batch=False, acceptance_test=False, preflight_only=False):
    return type(
        "Args",
        (),
        {
            "lead_report": None,
            "plan_only": False,
            "plan": str(plan_path),
            "execute": execute,
            "dry_run": False,
            "preflight_only": preflight_only,
            "acceptance_test": acceptance_test,
            "acceptance_max": None,
            "confirm_send": confirm_send,
            "yes_batch": yes_batch,
            "max_leads": 5,
            "daily_limit": 10,
            "interval_seconds": 0,
            "min_confidence": 0.9,
            "history_path": str(tmp_path / "history.jsonl"),
            "output_dir": str(tmp_path),
            "single_artifacts_dir": str(tmp_path / "replies"),
            "target_policy": "allowlist",
            "allow_source_url": [TEST_SOURCE_URL],
            "owned_source_id": [],
            "tenant_id": None,
        },
    )()
