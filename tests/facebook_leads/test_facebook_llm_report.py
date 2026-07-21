import argparse
import asyncio
import json
from dataclasses import replace

import pytest

import scripts.facebook_lead_scan as lead_scan
import scripts.facebook_reply_one as reply_cli
from src.facebook_leads.facebook.llm_models import failed_review
from src.facebook_leads.facebook.llm_review import (
    apply_review_to_leads,
    build_llm_review_summary,
    review_leads_with_llm_detailed,
)
from src.facebook_leads.facebook.report import build_lead_report, render_lead_report_html
from tests.facebook_leads.test_facebook_llm_review import FakeLLM, review_response
from tests.facebook_leads.test_facebook_report import scan_payload


def reviewed_report():
    report = build_lead_report(scan_payload())
    leads = [lead for content in report.contents for lead in content.leads]
    llm_result = asyncio.run(review_leads_with_llm_detailed(leads, llm_client=FakeLLM([review_response(len(leads))])))
    reviewed = apply_review_to_leads(leads, llm_result["reviewed"])
    offset = 0
    for content in report.contents:
        count = len(content.leads)
        content.leads = reviewed[offset : offset + count]
        offset += count
    return report


def test_json_contains_llm_review_and_final_fields():
    data = reviewed_report().to_dict()
    lead = data["contents"][0]["leads"][0]

    assert lead["llm_review"]["status"] == "success"
    assert lead["final_is_lead"] is True
    assert lead["final_intent_level"] == "high"
    assert lead["final_suggested_reply"]
    assert lead["decision_source"] == "llm"
    assert lead["rule_intent_score"] == lead["intent_score"]


def test_html_shows_ai_review_reply_and_copy_button():
    html = render_lead_report_html(reviewed_report())

    assert "AI 复核" in html
    assert "建议回复" in html
    assert "复制建议回复" in html
    assert "规则判断" in html
    assert "navigator.clipboard.writeText" in html


def test_html_shows_llm_disabled_status_and_method_note():
    html = render_lead_report_html(build_lead_report(scan_payload()))

    assert "LLM 复核：未启用" in html
    assert "本次未启用大语言模型复核" in html
    assert "本阶段未调用大语言模型" not in html


def test_success_report_summary_is_serialized_and_rendered():
    report = reviewed_report()
    leads = [lead for content in report.contents for lead in content.leads]
    report.llm_review = build_llm_review_summary(
        enabled=True,
        model="fake-model",
        candidate_count=len(leads),
        batches=[{"candidate_count": len(leads), "status": "success", "item_statuses": ["success"] * len(leads)}],
        batch_size=10,
        concurrency=2,
        elapsed_ms=123,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
    )

    data = report.to_dict()
    html = render_lead_report_html(report)

    assert data["llm_review"]["status"] == "success"
    assert data["llm_review"]["concurrency"] == 2
    assert data["llm_review"]["total_tokens"] == 15
    assert "LLM 复核：已完成" in html
    assert "模型：fake-model" in html
    assert "本次未启用大语言模型复核" not in html


def test_partial_report_summary_renders_fallback_status():
    report = reviewed_report()
    leads = [lead for content in report.contents for lead in content.leads]
    fallback = replace(
        leads[0],
        llm_review=failed_review(leads[0].comment_fingerprint, "batch timed out", status="timeout").to_dict(),
        llm_review_status="timeout",
        final_is_lead=leads[0].intent_score > 0,
        final_intent_level=leads[0].intent_level,
        final_intent_types=[category.lower() for category in leads[0].matched_categories],
        final_reason_zh=None,
        final_suggested_reply=None,
        decision_source="rule_fallback",
    )
    report.contents[0].leads[0] = fallback
    report.llm_review = build_llm_review_summary(
        enabled=True,
        model="fake-model",
        candidate_count=len(leads),
        batches=[
            {"candidate_count": 1, "status": "timeout", "item_statuses": ["timeout"]},
            {"candidate_count": len(leads) - 1, "status": "success", "item_statuses": ["success"] * (len(leads) - 1)},
        ],
        batch_size=1,
        concurrency=2,
        elapsed_ms=321,
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
    )

    html = render_lead_report_html(report)

    assert "LLM 复核：部分完成" in html
    assert "Fallback：1" in html
    assert "AI 复核：超时，已回退规则判断" in html
    assert "未成功复核的候选已保留规则判断结果" in html


def test_lead_scan_llm_review_default_is_off(monkeypatch, tmp_path):
    async def fake_scan(args):
        artifact_dir = tmp_path / "run"
        artifact_dir.mkdir()
        return {
            **scan_payload(),
            "diagnostics": {"artifact_dir": str(artifact_dir), "result_path": str(artifact_dir / "result.json")},
        }

    monkeypatch.setattr(lead_scan, "run_cli_scan", fake_scan)
    payload = asyncio.run(
        lead_scan.run_lead_scan(
            argparse.Namespace(
                keyword="car detailing",
                content_limit=1,
                comment_limit=10,
                max_scrolls=1,
                max_expand_clicks=1,
                current_page_only=False,
                output_dir=str(tmp_path),
                output=None,
                llm_review=False,
                llm_batch_size=10,
                llm_model=None,
                llm_client=None,
            )
        )
    )

    assert payload["diagnostics"]["llm_called"] is False
    assert payload["lead_report"]["contents"][0]["leads"][0]["llm_review"] is None


def test_lead_scan_llm_review_uses_batches(monkeypatch, tmp_path):
    async def fake_scan(args):
        artifact_dir = tmp_path / "run"
        artifact_dir.mkdir()
        return {
            **scan_payload(),
            "diagnostics": {"artifact_dir": str(artifact_dir), "result_path": str(artifact_dir / "result.json")},
        }

    async def fake_review(leads, **kwargs):
        result = await review_leads_with_llm_detailed(
            leads,
            llm_client=FakeLLM([review_response(2), review_response(1)]),
            batch_size=2,
        )
        return result

    monkeypatch.setattr(lead_scan, "run_cli_scan", fake_scan)
    monkeypatch.setattr(lead_scan, "review_leads_with_llm_detailed", fake_review)
    payload = asyncio.run(
        lead_scan.run_lead_scan(
            argparse.Namespace(
                keyword="car detailing",
                content_limit=1,
                comment_limit=10,
                max_scrolls=1,
                max_expand_clicks=1,
                current_page_only=False,
                output_dir=str(tmp_path),
                output=None,
                llm_review=True,
                llm_batch_size=2,
                llm_model="fake-model",
                llm_client=FakeLLM([]),
            )
        )
    )

    assert payload["diagnostics"]["llm_called"] is True
    assert payload["diagnostics"]["llm_review"]["llm_call_count"] == 2
    assert payload["lead_report"]["contents"][0]["leads"][0]["llm_review"]["status"] == "success"


def test_use_suggested_reply_reads_report_value(tmp_path):
    report = reviewed_report().to_dict()
    path = tmp_path / "lead_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    req = reply_cli.build_reply_request(
        argparse.Namespace(
            lead_report=str(path),
            lead_index=1,
            reply_text=None,
            use_suggested_reply=True,
            confirm_send=False,
            yes=False,
            keep_filled=False,
            allow_duplicate=False,
            source_content_url=None,
            direct_comment_url=None,
            comment_id=None,
            author_name=None,
            comment_text=None,
            fingerprint=None,
        )
    )

    assert req.reply_text == "Hi! Please send us a DM for pricing details."
    assert req.confirm_send is False


def test_use_suggested_reply_missing_value_errors(tmp_path):
    report = scan_payload()
    report = build_lead_report(report).to_dict()
    path = tmp_path / "lead_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="suggested_reply"):
        reply_cli.build_reply_request(
            argparse.Namespace(
                lead_report=str(path),
                lead_index=1,
                reply_text=None,
                use_suggested_reply=True,
                confirm_send=False,
                yes=False,
                keep_filled=False,
                allow_duplicate=False,
                source_content_url=None,
                direct_comment_url=None,
                comment_id=None,
                author_name=None,
                comment_text=None,
                fingerprint=None,
            )
        )
