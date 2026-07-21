import asyncio
import json

import pytest

from src.facebook_leads.facebook.intent import LeadIntentClassifier
from src.facebook_leads.facebook.llm_review import (
    resolve_llm_concurrency,
    resolve_llm_timeout_seconds,
    review_leads_with_llm_detailed,
)
from src.facebook_leads.facebook.models import FacebookComment


class FakeMessage:
    def __init__(self, content, usage=None):
        self.content = content
        self.response_metadata = {"token_usage": usage} if usage is not None else {}


class FakeLLM:
    def __init__(self, responses=None, exc=None):
        self.responses = list(responses or [])
        self.exc = exc
        self.calls = []
        self.model_name = "fake-model"

    async def ainvoke(self, messages):
        self.calls.append(messages)
        if self.exc:
            raise self.exc
        return self.responses.pop(0)


class DelayedFakeLLM(FakeLLM):
    def __init__(self, responses=None, delay=0.0):
        super().__init__(responses=responses)
        self.delay = delay
        self.active = 0
        self.max_active = 0

    async def ainvoke(self, messages):
        self.calls.append(messages)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delay)
            return self.responses.pop(0)
        finally:
            self.active -= 1


def make_lead(number=1):
    comment = FacebookComment(
        comment_id=f"c{number}",
        author_name="Alice",
        author_url=None,
        text="How much for BMW 218I?",
        timestamp_text=None,
        comment_url=None,
        is_reply=False,
        parent_comment_id=None,
        source_content_url="https://www.facebook.com/reel/1",
        fingerprint=f"fp{number}",
        direct_comment_url=f"https://www.facebook.com/reel/1?comment_id=c{number}",
    )
    lead = LeadIntentClassifier().classify_comment(
        comment,
        {
            "content_type": "reel",
            "text_preview": "Car detailing promo",
            "author_name": "Shop",
            "discovered_url": "https://www.facebook.com/reel/1",
            "final_url": "https://www.facebook.com/reel/1",
        },
    )
    assert lead is not None
    return lead


def review_response(count):
    return FakeMessage(
        json.dumps(
            {
                "results": [
                    {
                        "index": index,
                        "is_lead": True,
                        "confidence": 0.9,
                        "intent_level": "high",
                        "intent_types": ["price"],
                        "reason_zh": "用户明确询问价格。",
                        "summary_zh": "询问 BMW 服务价格。",
                        "suggested_reply": "Hi! Please send us a DM for pricing details.",
                        "reply_language": "en",
                        "should_reply": True,
                        "risk_flags": [],
                    }
                    for index in range(1, count + 1)
                ]
            }
        ),
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )


def test_single_batch_review_success():
    llm = FakeLLM([review_response(2)])

    result = asyncio.run(review_leads_with_llm_detailed([make_lead(1), make_lead(2)], llm_client=llm, batch_size=10))

    assert len(llm.calls) == 1
    assert len(result["reviewed"]) == 2
    assert result["reviewed"][0].llm_review.status == "success"
    assert result["reviewed"][0].final_is_lead is True
    assert result["reviewed"][0].decision_source == "llm"
    assert result["reviewed"][0].rule_intent_score > 0
    assert result["timing"]["llm_total_tokens"] == 15


def test_multi_batch_review_respects_batch_size():
    llm = FakeLLM([review_response(2), review_response(1)])

    result = asyncio.run(review_leads_with_llm_detailed([make_lead(1), make_lead(2), make_lead(3)], llm_client=llm, batch_size=2))

    assert len(llm.calls) == 2
    assert [batch["batch_size"] for batch in result["diagnostics"]["batches"]] == [2, 1]


def test_invalid_json_retries_then_succeeds():
    llm = FakeLLM([FakeMessage("{not-json"), review_response(1)])

    result = asyncio.run(review_leads_with_llm_detailed([make_lead()], llm_client=llm, batch_size=1))

    assert len(llm.calls) == 2
    assert result["reviewed"][0].llm_review.status == "success"
    assert result["diagnostics"]["batches"][0]["attempts"] == 2


def test_timeout_falls_back_to_rule_result():
    llm = FakeLLM(exc=TimeoutError("timeout"))

    result = asyncio.run(review_leads_with_llm_detailed([make_lead()], llm_client=llm, batch_size=1))

    reviewed = result["reviewed"][0]
    assert reviewed.llm_review.status == "timeout"
    assert reviewed.final_is_lead is True
    assert reviewed.final_intent_level == reviewed.rule_intent_level
    assert reviewed.decision_source == "rule_fallback"


def test_concurrency_one_keeps_batches_serial():
    llm = DelayedFakeLLM([review_response(1), review_response(1)], delay=0.01)

    result = asyncio.run(
        review_leads_with_llm_detailed(
            [make_lead(1), make_lead(2)],
            llm_client=llm,
            batch_size=1,
            concurrency=1,
        )
    )

    assert llm.max_active == 1
    assert [item.lead.comment_fingerprint for item in result["reviewed"]] == ["fp1", "fp2"]


def test_concurrency_two_allows_two_batches_and_preserves_order():
    llm = DelayedFakeLLM([review_response(1), review_response(1)], delay=0.01)

    result = asyncio.run(
        review_leads_with_llm_detailed(
            [make_lead(1), make_lead(2)],
            llm_client=llm,
            batch_size=1,
            concurrency=2,
        )
    )

    assert llm.max_active == 2
    assert [item.lead.comment_fingerprint for item in result["reviewed"]] == ["fp1", "fp2"]


def test_one_success_one_timeout_makes_partial_summary():
    class MixedLLM:
        model_name = "fake-model"

        def __init__(self):
            self.calls = 0

        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return review_response(1)
            await asyncio.sleep(0.05)
            return review_response(1)

    result = asyncio.run(
        review_leads_with_llm_detailed(
            [make_lead(1), make_lead(2)],
            llm_client=MixedLLM(),
            batch_size=1,
            concurrency=2,
            timeout_seconds=0.01,
        )
    )

    assert result["summary"]["status"] == "partial"
    assert result["summary"]["success_count"] == 1
    assert result["summary"]["timeout_count"] == 1
    assert result["summary"]["fallback_count"] == 1


def test_all_timeout_keeps_reportable_failed_summary():
    llm = DelayedFakeLLM([review_response(1), review_response(1)], delay=0.05)

    result = asyncio.run(
        review_leads_with_llm_detailed(
            [make_lead(1), make_lead(2)],
            llm_client=llm,
            batch_size=1,
            concurrency=2,
            timeout_seconds=0.01,
        )
    )

    assert result["summary"]["status"] == "failed"
    assert result["summary"]["timeout_count"] == 2
    assert all(item.decision_source == "rule_fallback" for item in result["reviewed"])


def test_wall_clock_timing_is_not_batch_elapsed_sum():
    llm = DelayedFakeLLM([review_response(1), review_response(1)], delay=0.05)

    result = asyncio.run(
        review_leads_with_llm_detailed(
            [make_lead(1), make_lead(2)],
            llm_client=llm,
            batch_size=1,
            concurrency=2,
        )
    )

    assert result["timing"]["llm_batch_elapsed_ms_total"] >= result["timing"]["llm_review_ms"]
    assert result["summary"]["elapsed_ms"] == result["timing"]["llm_review_ms"]


def test_usage_missing_keeps_token_totals_null():
    llm = FakeLLM([FakeMessage(review_response(1).content, usage=None)])

    result = asyncio.run(review_leads_with_llm_detailed([make_lead()], llm_client=llm, batch_size=1))

    assert result["timing"]["llm_prompt_tokens"] is None
    assert result["summary"]["total_tokens"] is None


def test_llm_concurrency_prefers_cli_over_env(monkeypatch):
    monkeypatch.setenv("FACEBOOK_LEADS_LLM_CONCURRENCY", "5")

    assert resolve_llm_concurrency(2) == 2


def test_llm_concurrency_reads_env_and_validates(monkeypatch):
    monkeypatch.setenv("FACEBOOK_LEADS_LLM_CONCURRENCY", "3")
    assert resolve_llm_concurrency() == 3

    monkeypatch.setenv("FACEBOOK_LEADS_LLM_CONCURRENCY", "0")
    with pytest.raises(ValueError, match="concurrency"):
        resolve_llm_concurrency()


def test_llm_timeout_prefers_cli_over_env(monkeypatch):
    monkeypatch.setenv("FACEBOOK_LEADS_LLM_TIMEOUT_SECONDS", "30")

    assert resolve_llm_timeout_seconds(10) == 10


def test_llm_timeout_reads_env_and_validates(monkeypatch):
    monkeypatch.setenv("FACEBOOK_LEADS_LLM_TIMEOUT_SECONDS", "45.5")
    assert resolve_llm_timeout_seconds() == 45.5

    monkeypatch.setenv("FACEBOOK_LEADS_LLM_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValueError, match="timeout"):
        resolve_llm_timeout_seconds()
