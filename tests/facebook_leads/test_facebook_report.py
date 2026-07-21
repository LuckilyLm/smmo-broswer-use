from src.facebook_leads.facebook.report import (
    build_lead_report,
    clean_comment_text,
    is_meaningful_content_preview,
    render_lead_report_html,
)


def scan_payload():
    return {
        "success": True,
        "stage": "completed",
        "keyword": "car detailing",
        "contents": [
            {
                "url": "https://www.facebook.com/reel/1",
                "content_type": "reel",
                "text_preview": "First & fast",
                "author_name": "Shop A",
            },
            {
                "url": "https://www.facebook.com/reel/2",
                "content_type": "reel",
                "text_preview": "Second",
                "author_name": None,
            },
        ],
        "comments": [
            {
                "comment_id": "c1",
                "author_name": "Alice",
                "author_url": "https://www.facebook.com/alice",
                "text": "How much?",
                "timestamp_text": "1h",
                "comment_url": "https://www.facebook.com/reel/1?comment_id=c1",
                "direct_comment_url": "https://www.facebook.com/reel/1?comment_id=c1",
                "comment_id_source": "comment_link",
                "is_reply": False,
                "parent_comment_id": None,
                "source_content_url": "https://www.facebook.com/reel/1",
                "fingerprint": "fp1",
            },
            {
                "comment_id": "c2",
                "author_name": "Bob",
                "author_url": None,
                "text": "price <script>alert(1)</script>",
                "timestamp_text": None,
                "comment_url": None,
                "is_reply": False,
                "parent_comment_id": None,
                "source_content_url": "https://www.facebook.com/reel/2",
                "fingerprint": "fp2",
            },
            {
                "comment_id": "c3",
                "author_name": "Carol",
                "author_url": None,
                "text": "Do you deliver?",
                "timestamp_text": None,
                "comment_url": None,
                "is_reply": False,
                "parent_comment_id": None,
                "source_content_url": "https://www.facebook.com/reel/2",
                "fingerprint": "fp3",
            },
        ],
        "timing": {"total_ms": 100},
        "diagnostics": {
            "result_path": "artifacts/result.json",
            "per_content": [
                {
                    "discovered_url": "https://www.facebook.com/reel/1",
                    "final_url": "https://www.facebook.com/reel/1",
                },
                {
                    "discovered_url": "https://www.facebook.com/reel/2",
                    "final_url": "https://www.facebook.com/reel/2",
                },
            ],
        },
    }


def test_report_groups_multiple_contents_and_source_urls():
    report = build_lead_report(scan_payload())

    assert report.scanned_content_count == 2
    assert report.scanned_comment_count == 3
    assert report.lead_candidate_count == 3
    assert report.contents[0].leads[0].source_content_url == "https://www.facebook.com/reel/1"
    assert report.contents[1].leads[0].source_content_url == "https://www.facebook.com/reel/2"


def test_lead_report_json_keeps_source_content_url():
    report = build_lead_report(scan_payload())
    data = report.to_dict()

    assert data["contents"][0]["leads"][0]["source_content_url"] == "https://www.facebook.com/reel/1"
    assert data["contents"][1]["leads"][0]["source_content_url"] == "https://www.facebook.com/reel/2"


def test_html_report_contains_multiple_source_sections_and_links():
    html = render_lead_report_html(build_lead_report(scan_payload()))

    assert html.count("打开 Facebook 原帖") == 2
    assert html.count("打开原帖") >= 4
    assert "https://www.facebook.com/reel/1" in html
    assert "https://www.facebook.com/reel/2" in html


def test_html_report_escapes_comment_and_preview():
    html = render_lead_report_html(build_lead_report(scan_payload()))

    assert "First &amp; fast" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_author_url_generates_link_and_missing_author_url_is_ok():
    html = render_lead_report_html(build_lead_report(scan_payload()))

    assert '<a href="https://www.facebook.com/alice"' in html
    assert "Carol" in html


def test_chinese_labels_are_used_for_content_level_and_categories():
    html = render_lead_report_html(build_lead_report(scan_payload()))

    assert "短视频" in html
    assert "中等意向" in html
    assert "购买意向" in html
    assert "价格咨询" in html
    assert "MEDIUM" not in html
    assert "BUY" not in html
    assert "PRICE" not in html


def test_lead_report_json_keeps_machine_fields_and_adds_chinese_labels():
    data = build_lead_report(scan_payload()).to_dict()
    lead = data["contents"][0]["leads"][0]

    assert lead["intent_level"] == "medium"
    assert lead["intent_level_label"] == "中等意向"
    assert lead["matched_categories"] == ["PRICE"]
    assert lead["matched_category_labels"] == ["价格咨询"]
    assert lead["source_content_type_label"] == "短视频"
    assert data["contents"][0]["content_type_label"] == "短视频"
    assert lead["comment_id"] == "c1"
    assert lead["comment_url"] == "https://www.facebook.com/reel/1?comment_id=c1"
    assert lead["direct_comment_url"] == "https://www.facebook.com/reel/1?comment_id=c1"
    assert lead["comment_id_source"] == "comment_link"


def test_html_report_displays_precise_comment_link_and_missing_fallback():
    html = render_lead_report_html(build_lead_report(scan_payload()))

    assert "精准定位评论" in html
    assert "查看该评论" in html
    assert "暂无法精准定位" in html
    assert "<th>评论链接</th>" in html


def test_html_report_does_not_repeat_author_name_in_comment_body():
    payload = scan_payload()
    payload["comments"][0]["author_name"] = "Justin Kwoh"
    payload["comments"][0]["author_url"] = "https://www.facebook.com/justin.kwoh?comment_id=c1"
    payload["comments"][0]["text"] = "Justin Kwoh\nHow much?"
    report = build_lead_report(payload)
    html = render_lead_report_html(report)
    lead = report.contents[0].leads[0]

    assert lead.author_name == "Justin Kwoh"
    assert lead.comment_text == "How much?"
    assert "未知用户" not in html.split("Justin Kwoh", 1)[0]
    assert '<a href="https://www.facebook.com/justin.kwoh?comment_id=c1"' in html
    assert '<div class="comment">How much?</div>' in html


def test_clean_comment_text_removes_facebook_ui_noise():
    text = "\n".join(
        [
            "Justin Kwoh",
            "·",
            "7周",
            "·",
            "作者",
            "What are the other charges like waxing and vacuum? Need buy package?",
            "查看翻译",
            "1",
        ]
    )

    assert clean_comment_text(text, author_name="Justin Kwoh") == (
        "What are the other charges like waxing and vacuum? Need buy package?"
    )


def test_clean_comment_text_keeps_real_numbers_inside_comment():
    assert clean_comment_text("How much for 2 cars?") == "How much for 2 cars?"


def test_content_preview_rejects_time_only_and_report_falls_back():
    payload = scan_payload()
    payload["contents"][0]["text_preview"] = "3天"
    report = build_lead_report(payload)

    assert is_meaningful_content_preview("5月17日") is False
    assert report.contents[0].text_preview == "Facebook 短视频"
    assert "Facebook 短视频" in render_lead_report_html(report)


def test_report_infers_reel_type_from_url_when_scan_type_is_unknown():
    payload = scan_payload()
    payload["contents"][0]["content_type"] = "unknown"
    payload["contents"][0]["text_preview"] = "Reels | Facebook"
    payload["diagnostics"]["per_content"][0]["content_type"] = "unknown"
    payload["diagnostics"]["per_content"][0]["final_url"] = "https://www.facebook.com/reel/1297294631902733"
    payload["comments"][0]["source_content_url"] = "https://www.facebook.com/reel/1297294631902733"

    report = build_lead_report(payload)
    data = report.to_dict()
    html = render_lead_report_html(report)

    assert data["contents"][0]["content_type"] == "reel"
    assert data["contents"][0]["content_type_label"] == "短视频"
    assert data["contents"][0]["text_preview"] == "Facebook 短视频"
    assert "未知内容" not in html.split("https://www.facebook.com/reel/1297294631902733", 1)[0]
    assert "短视频" in html


def test_lead_report_json_content_type_uses_final_detected_type():
    payload = scan_payload()
    payload["contents"][0]["content_type"] = "post"
    payload["diagnostics"]["per_content"][0]["content_type"] = "post"
    payload["diagnostics"]["per_content"][0]["final_url"] = "https://www.facebook.com/reels/777"
    payload["comments"][0]["source_content_url"] = "https://www.facebook.com/reels/777"

    data = build_lead_report(payload).to_dict()

    assert data["contents"][0]["content_type"] == "reel"
    assert data["contents"][0]["leads"][0]["source_content_type"] == "reel"
