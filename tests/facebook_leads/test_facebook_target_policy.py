from src.facebook_leads.facebook.target_policy import build_target_policy_config, evaluate_source_policy


def lead(source_url="https://www.facebook.com/BrandPage/posts/1", author="Brand Page"):
    return {"source_content_url": source_url, "source_author_name": author}


def test_owned_only_allows_owned_source():
    config = build_target_policy_config(policy="owned_only", owned_source_ids=["brand page"])

    decision = evaluate_source_policy(lead(), config)

    assert decision["ownership_status"] == "owned"
    assert decision["reply_allowed"] is True


def test_owned_only_blocks_third_party():
    config = build_target_policy_config(policy="owned_only", owned_source_ids=["brand page"])

    decision = evaluate_source_policy(lead(author="Other Seller"), config)

    assert decision["ownership_status"] == "third_party"
    assert decision["reply_allowed"] is False


def test_allowlist_allows_matching_source_url():
    url = "https://www.facebook.com/reel/1408034480710164"
    config = build_target_policy_config(policy="allowlist", allowed_source_urls=[url])

    decision = evaluate_source_policy(lead(source_url=url), config)

    assert decision["ownership_status"] == "allowlisted"
    assert decision["reply_allowed"] is True


def test_allowlist_blocks_non_allowed_source_url():
    config = build_target_policy_config(policy="allowlist", allowed_source_urls=["https://www.facebook.com/reel/1"])

    decision = evaluate_source_policy(lead(source_url="https://www.facebook.com/reel/2"), config)

    assert decision["reply_allowed"] is False
    assert decision["ownership_reason"] == "source_not_allowlisted"


def test_discovery_only_blocks_all_sources():
    config = build_target_policy_config(policy="discovery_only", allowed_source_urls=["https://www.facebook.com/reel/1"])

    decision = evaluate_source_policy(lead(source_url="https://www.facebook.com/reel/1"), config)

    assert decision["ownership_status"] == "unknown"
    assert decision["reply_allowed"] is False


def test_unknown_ownership_blocks_reply():
    config = build_target_policy_config(policy="owned_only", owned_source_ids=["brand page"])

    decision = evaluate_source_policy(lead(source_url="https://www.facebook.com/reel/1", author=None), config)

    assert decision["ownership_status"] == "unknown"
    assert decision["reply_allowed"] is False
