import asyncio

from src.facebook_leads.facebook.content_metadata import (
    detect_content_type,
    detect_content_type_from_url,
    extract_content_metadata,
    fallback_content_preview,
    is_meaningful_content_preview,
)
from src.facebook_leads.facebook.models import FacebookContentCandidate


class FakePage:
    def __init__(
        self,
        url="https://www.facebook.com/",
        content_type=None,
        content_preview=None,
        content_author=None,
    ):
        self.url = url
        self.content_type = content_type
        self.content_preview = content_preview
        self.content_author = content_author


def test_detect_content_type_from_common_urls():
    cases = {
        "https://www.facebook.com/reel/1297294631902733": "reel",
        "https://www.facebook.com/reels/1297294631902733": "reel",
        "https://www.facebook.com/page/videos/123": "video",
        "https://www.facebook.com/page/posts/123": "post",
        "https://www.facebook.com/story.php?story_fbid=1&id=2": "post",
        "https://www.facebook.com/permalink.php?story_fbid=1&id=2": "post",
    }

    for url, expected in cases.items():
        assert detect_content_type_from_url(url) == expected


def test_discovered_type_is_not_overwritten_by_unknown_urls():
    content_type = asyncio.run(
        detect_content_type(
            "https://www.facebook.com/somewhere",
            discovered_type="post",
            final_url="https://www.facebook.com/somewhere",
        )
    )

    assert content_type == "post"


def test_final_url_type_has_priority_after_open():
    content_type = asyncio.run(
        detect_content_type(
            "https://www.facebook.com/somewhere",
            discovered_type="post",
            final_url="https://www.facebook.com/reel/123",
        )
    )

    assert content_type == "reel"


def test_preview_filter_rejects_time_and_ui_text():
    assert is_meaningful_content_preview("3天") is False
    assert is_meaningful_content_preview("5月17日") is False
    assert is_meaningful_content_preview("Today") is False
    assert is_meaningful_content_preview("(5) Facebook") is False
    assert is_meaningful_content_preview("Reels | Facebook") is False
    assert is_meaningful_content_preview("Like") is False
    assert is_meaningful_content_preview("查看翻译") is False
    assert is_meaningful_content_preview("Ceramic coating transformation for BMW") is True


def test_content_type_fallback_preview_labels():
    assert fallback_content_preview("reel") == "Facebook 短视频"
    assert fallback_content_preview("post") == "Facebook 帖子"
    assert fallback_content_preview("video") == "Facebook 视频"
    assert fallback_content_preview("unknown") == "Facebook 内容"


def test_extract_content_metadata_keeps_content_author_separate_from_comment_author():
    page = FakePage(
        url="https://www.facebook.com/reel/123",
        content_preview="Ceramic coating transformation for BMW",
        content_author="Detailing Studio",
    )
    candidate = FacebookContentCandidate(
        url="https://www.facebook.com/unknown",
        content_type="unknown",
        text_preview="3天",
        author_name=None,
    )

    enriched, diag = asyncio.run(extract_content_metadata(page, candidate))

    assert enriched.content_type == "reel"
    assert enriched.text_preview == "Ceramic coating transformation for BMW"
    assert enriched.author_name == "Detailing Studio"
    assert diag["author_name"] == "Detailing Studio"
    assert "comment_author" not in diag


def test_extract_content_metadata_rejects_owner_profile_ui_author_and_falls_back():
    page = FakePage(
        url="https://www.facebook.com/reel/123",
        content_preview="(5) Facebook",
        content_author="查看所有者个人主页",
    )
    candidate = FacebookContentCandidate(url="https://www.facebook.com/reel/123")

    enriched, diag = asyncio.run(extract_content_metadata(page, candidate))

    assert enriched.content_type == "reel"
    assert enriched.text_preview == "Facebook 短视频"
    assert enriched.author_name is None
    assert diag["text_preview_source"] == "fallback"
    assert diag["author_source"] == "missing"
