from src.facebook_leads.facebook.intent import LeadIntentClassifier, normalize_comment_text, score_to_level
from src.facebook_leads.facebook.models import FacebookComment


def make_comment(text, fingerprint="fp", source_url="https://www.facebook.com/reel/1"):
    return FacebookComment(
        comment_id=None,
        author_name="John",
        author_url=None,
        text=text,
        timestamp_text=None,
        comment_url=None,
        is_reply=False,
        parent_comment_id=None,
        source_content_url=source_url,
        fingerprint=fingerprint,
    )


def classify(text):
    return LeadIntentClassifier().classify_comment(make_comment(text))


def test_price_phrases_match_price_category():
    assert "PRICE" in classify("how much?").matched_categories
    assert "PRICE" in classify("price please").matched_categories


def test_buy_phrases_match_buy_category():
    assert "BUY" in classify("where can i buy").matched_categories
    assert "BUY" in classify("i need one").matched_categories


def test_delivery_phrases_match_delivery_category():
    assert "DELIVERY" in classify("delivery?").matched_categories
    assert "DELIVERY" in classify("do you ship").matched_categories


def test_location_and_contact_match():
    assert "LOCATION" in classify("location please").matched_categories
    assert "CONTACT" in classify("pm").matched_categories


def test_pm_does_not_duplicate_or_match_inside_example():
    lead = classify("PM")

    assert lead.intent_score == 3
    assert len([item for item in lead.matched_keywords if item.normalized_keyword == "pm"]) == 1
    assert classify("example") is None


def test_short_comments_are_not_filtered():
    assert classify("Price?").intent_level == "medium"
    assert classify("PM").intent_level == "medium"


def test_multilingual_keywords_match():
    assert "PRICE" in classify("Magkano?").matched_categories
    assert "PRICE" in classify("harga").matched_categories
    assert "BUY" in classify("Count me in").matched_categories


def test_multiple_categories_increase_score_and_level():
    lead = classify("How much and do you deliver?")

    assert set(lead.matched_categories) >= {"PRICE", "DELIVERY"}
    assert lead.intent_score >= 7
    assert lead.intent_level == "high"


def test_score_levels():
    assert score_to_level(6) == "high"
    assert score_to_level(3) == "medium"
    assert score_to_level(1) == "low"
    assert score_to_level(0) == "none"


def test_none_comment_does_not_enter_candidates():
    assert classify("nice video") is None


def test_fingerprint_and_source_url_are_preserved():
    comment = make_comment("How much?", fingerprint="abc", source_url="https://www.facebook.com/reel/99")
    comment = FacebookComment(
        **{
            **comment.to_dict(),
            "comment_id": "c99",
            "comment_url": "https://www.facebook.com/reel/99?comment_id=c99",
            "direct_comment_url": "https://www.facebook.com/reel/99?comment_id=c99",
            "comment_id_source": "comment_link",
        }
    )
    lead = LeadIntentClassifier().classify_comment(comment)

    assert lead.comment_fingerprint == "abc"
    assert lead.source_content_url == "https://www.facebook.com/reel/99"
    assert lead.comment_id == "c99"
    assert lead.comment_url == "https://www.facebook.com/reel/99?comment_id=c99"
    assert lead.direct_comment_url == "https://www.facebook.com/reel/99?comment_id=c99"
    assert lead.comment_locator_data["comment_id"] == "c99"


def test_false_positive_price_context_is_downgraded():
    lead = classify("stock price and economy are difficult")

    assert lead.is_false_positive is True
    assert lead.intent_level == "low"


def test_availability_queries_are_lead_candidates():
    for text in ["Available pa po?", "Still available?", "is it still available?", "Is it avail?", "in stock?"]:
        lead = classify(text)

        assert lead is not None
        assert "AVAILABILITY" in lead.matched_categories
        assert lead.intent_level in {"medium", "high"}


def test_availability_synonyms_are_deduplicated_to_specific_phrase():
    lead = classify("Available pa po?")

    assert len(lead.raw_matched_keywords) >= 3
    assert lead.effective_matched_keywords == ["available pa po"]
    assert set(lead.deduplicated_keywords) >= {"available", "available pa"}
    assert lead.score_breakdown["AVAILABILITY"] == 4
    assert lead.score_breakdown["total"] == 6


def test_still_available_prefers_specific_phrase():
    lead = classify("Still available?")

    assert "available" in lead.raw_matched_keywords
    assert lead.effective_matched_keywords == ["still available"]
    assert lead.score_breakdown["total"] == 6


def test_product_info_queries_are_lead_candidates():
    for text in ["What brand?", "brand new po ba?", "Which model?", "What model?"]:
        lead = classify(text)

        assert lead is not None
        assert "PRODUCT_INFO" in lead.matched_categories


def test_product_info_deduplicates_brand_phrase():
    lead = classify("What brand?")

    assert set(lead.raw_matched_keywords) >= {"what brand", "brand"}
    assert lead.effective_matched_keywords == ["what brand"]
    assert lead.score_breakdown["PRODUCT_INFO"] == 2


def test_praise_noise_still_not_leads():
    for text in ["Wow", "Gorgeous", "very nice", "I love you", "looks great"]:
        assert classify(text) is None


def test_cross_category_matches_still_stack():
    lead = classify("Price and delivery?")

    assert set(lead.matched_categories) >= {"PRICE", "DELIVERY"}
    assert lead.score_breakdown["PRICE"] == 5
    assert lead.score_breakdown["DELIVERY"] == 4


def test_normalize_comment_text_compacts_unicode_and_spaces():
    assert normalize_comment_text("  Price\u2019s   OK? ") == "price's ok?"
