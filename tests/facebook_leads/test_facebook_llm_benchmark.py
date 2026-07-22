import argparse
import asyncio
import json
from pathlib import Path

import scripts.facebook_llm_benchmark as benchmark
from src.facebook_leads.facebook.llm_review import LLM_REVIEW_PROMPT_VERSION
from tests.facebook_leads.test_facebook_report import scan_payload


def test_benchmark_does_not_import_browser_or_safe_reply():
    source = Path("scripts/facebook_llm_benchmark.py").read_text(encoding="utf-8")

    assert "browser_adapter" not in source
    assert "facebook_readonly_scan" not in source
    assert "facebook_reply_one" not in source
    assert "reply_to_comment" not in source
    assert "Safe Reply" not in source


def test_benchmark_writes_json_and_calculates_metrics(monkeypatch, tmp_path):
    input_path = tmp_path / "result.json"
    input_path.write_text(json.dumps(scan_payload()), encoding="utf-8")

    async def fake_review(leads, **kwargs):
        return {
            "reviewed": [],
            "timing": {"llm_review_ms": 1000},
            "diagnostics": {
                "batches": [
                    {
                        "batch_index": 1,
                        "candidate_count": 2,
                        "batch_size": 2,
                        "status": "success",
                        "item_statuses": ["success", "success"],
                        "prompt_version": LLM_REVIEW_PROMPT_VERSION,
                        "payload_chars": 100,
                        "prompt_chars": 500,
                        "prompt_estimated_tokens": 125,
                    }
                ]
            },
            "summary": {
                "model": kwargs["model_name"],
                "prompt_version": LLM_REVIEW_PROMPT_VERSION,
                "candidate_count": len(leads),
                "success_count": 2,
                "fallback_count": 0,
                "call_count": 1,
                "prompt_tokens": 60,
                "completion_tokens": 30,
                "total_tokens": 90,
                "elapsed_ms": 1000,
            },
        }

    monkeypatch.setattr(benchmark, "review_leads_with_llm_detailed", fake_review)

    payload = asyncio.run(
        benchmark.run_benchmark(
            argparse.Namespace(
                input=str(input_path),
                model="fake-model",
                batch_size=2,
                concurrency=1,
                timeout_seconds=30,
                max_batch_chars=1000,
                limit=2,
                output_dir=str(tmp_path / "benchmarks"),
            )
        )
    )

    assert payload["model"] == "fake-model"
    assert payload["candidate_count"] == 2
    assert payload["batch_count"] == 1
    assert payload["prompt_tokens"] == 60
    assert payload["completion_tokens"] == 30
    assert payload["total_tokens"] == 90
    assert payload["tokens_per_candidate"] == 45
    assert payload["ms_per_candidate"] is not None
    assert payload["no_browser_started"] is True
    assert payload["no_facebook_write_operations"] is True
    output_path = Path(payload["output_json"])
    assert output_path.exists()
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["total_tokens"] == 90


def test_benchmark_keeps_token_fields_null_when_usage_missing(monkeypatch, tmp_path):
    input_path = tmp_path / "result.json"
    input_path.write_text(json.dumps(scan_payload()), encoding="utf-8")

    async def fake_review(leads, **kwargs):
        return {
            "reviewed": [],
            "timing": {},
            "diagnostics": {"batches": []},
            "summary": {
                "model": kwargs["model_name"],
                "prompt_version": LLM_REVIEW_PROMPT_VERSION,
                "success_count": 0,
                "fallback_count": len(leads),
                "call_count": 0,
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "elapsed_ms": 0,
            },
        }

    monkeypatch.setattr(benchmark, "review_leads_with_llm_detailed", fake_review)

    payload = asyncio.run(
        benchmark.run_benchmark(
            argparse.Namespace(
                input=str(input_path),
                model="fake-model",
                batch_size=10,
                concurrency=1,
                timeout_seconds=30,
                max_batch_chars=1000,
                limit=1,
                output_dir=str(tmp_path / "benchmarks"),
            )
        )
    )

    assert payload["prompt_tokens"] is None
    assert payload["completion_tokens"] is None
    assert payload["total_tokens"] is None
    assert payload["tokens_per_candidate"] is None
