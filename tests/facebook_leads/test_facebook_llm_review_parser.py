import json

from src.facebook_leads.facebook.llm_review import parse_llm_review_response
from tests.facebook_leads.test_facebook_llm_review import make_lead, review_response


def test_parser_accepts_strict_json():
    reviewed = parse_llm_review_response(review_response(1).content, [make_lead()])

    assert reviewed[0].llm_review.status == "success"
    assert reviewed[0].llm_review.suggested_reply == "Hi! Please send us a DM for pricing details."


def test_parser_accepts_markdown_code_block():
    content = "```json\n" + review_response(1).content + "\n```"

    reviewed = parse_llm_review_response(content, [make_lead()])

    assert reviewed[0].llm_review.intent_level == "high"


def test_missing_result_falls_back_per_lead():
    content = json.dumps({"results": []})

    reviewed = parse_llm_review_response(content, [make_lead()])

    assert reviewed[0].llm_review.status == "missing"
    assert reviewed[0].decision_source == "rule_fallback"


def test_invalid_confidence_marks_item_failed():
    payload = json.loads(review_response(1).content)
    payload["results"][0]["confidence"] = 2

    reviewed = parse_llm_review_response(json.dumps(payload), [make_lead()])

    assert reviewed[0].llm_review.status == "failed"
    assert "confidence" in reviewed[0].llm_review.error


def test_invalid_intent_level_marks_item_failed():
    payload = json.loads(review_response(1).content)
    payload["results"][0]["intent_level"] = "urgent"

    reviewed = parse_llm_review_response(json.dumps(payload), [make_lead()])

    assert reviewed[0].llm_review.status == "failed"
    assert "intent_level" in reviewed[0].llm_review.error


def test_high_risk_flag_disables_should_reply():
    payload = json.loads(review_response(1).content)
    payload["results"][0]["risk_flags"] = ["spam"]
    payload["results"][0]["should_reply"] = True

    reviewed = parse_llm_review_response(json.dumps(payload), [make_lead()])

    assert reviewed[0].llm_review.status == "success"
    assert reviewed[0].llm_review.should_reply is False
