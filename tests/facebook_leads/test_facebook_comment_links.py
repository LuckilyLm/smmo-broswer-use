import asyncio

from src.facebook_leads.facebook.comment_links import (
    build_direct_comment_url,
    extract_comment_id_from_url,
    extract_comment_permalink_from_node,
    resolve_comment_links,
)
from src.facebook_leads.facebook.comments import extract_comments, locate_comment_node


def test_extract_comment_id_from_url_supports_facebook_query_keys():
    assert extract_comment_id_from_url("https://www.facebook.com/post?comment_id=123") == "123"
    assert extract_comment_id_from_url("https://www.facebook.com/post?reply_comment_id=456") == "456"
    assert extract_comment_id_from_url("https://www.facebook.com/permalink.php?story_fbid=789&id=1") == "789"


def test_extract_comment_id_from_author_url_without_using_it_as_comment_url():
    result = resolve_comment_links(
        source_content_url="https://www.facebook.com/reel/1",
        author_url="https://www.facebook.com/alice?comment_id=abc",
    )

    assert result.comment_id == "abc"
    assert result.comment_url is None
    assert result.comment_id_source == "author_url"


def test_node_permalink_priority_prefers_comment_id_link():
    node = {
        "links": [
            {"href": "https://www.facebook.com/permalink.php?story_fbid=story&id=1"},
            {"href": "https://www.facebook.com/reel/1?comment_id=comment-1"},
        ]
    }

    assert extract_comment_permalink_from_node(node) == "https://www.facebook.com/reel/1?comment_id=comment-1"


def test_build_direct_comment_url_uses_permalink_before_generating_candidate():
    comment_url = "https://www.facebook.com/reel/1?comment_id=from-link"

    assert build_direct_comment_url("https://www.facebook.com/reel/1", "generated", comment_url) == comment_url
    assert (
        build_direct_comment_url("https://www.facebook.com/reel/1?existing=1", "generated")
        == "https://www.facebook.com/reel/1?existing=1&comment_id=generated"
    )


class FakePage:
    def __init__(self, records):
        self.comment_records = records


def test_author_url_is_not_misused_as_comment_url_during_extraction():
    page = FakePage(
        [
            {
                "comment_id": None,
                "author_name": "Alice",
                "author_url": "https://www.facebook.com/alice?comment_id=from-author",
                "text": "How much?",
                "timestamp_text": None,
                "comment_url": None,
                "is_reply": False,
                "parent_comment_id": None,
            }
        ]
    )

    comments = asyncio.run(extract_comments(page, "https://www.facebook.com/reel/1"))

    assert comments[0].comment_id == "from-author"
    assert comments[0].author_url == "https://www.facebook.com/alice?comment_id=from-author"
    assert comments[0].comment_url is None
    assert comments[0].direct_comment_url == "https://www.facebook.com/reel/1?comment_id=from-author"


def test_multiple_comment_records_do_not_mix_comment_ids():
    page = FakePage(
        [
            {
                "comment_id": None,
                "author_name": "Alice",
                "author_url": None,
                "text": "How much?",
                "timestamp_text": None,
                "comment_url": "https://www.facebook.com/reel/1?comment_id=a",
                "is_reply": False,
                "parent_comment_id": None,
            },
            {
                "comment_id": None,
                "author_name": "Bob",
                "author_url": None,
                "text": "PM",
                "timestamp_text": None,
                "comment_url": "https://www.facebook.com/reel/1?comment_id=b",
                "is_reply": False,
                "parent_comment_id": None,
            },
        ]
    )

    comments = asyncio.run(extract_comments(page, "https://www.facebook.com/reel/1"))

    assert [comment.comment_id for comment in comments] == ["a", "b"]
    assert [comment.comment_url for comment in comments] == [
        "https://www.facebook.com/reel/1?comment_id=a",
        "https://www.facebook.com/reel/1?comment_id=b",
    ]


class FakeLocator:
    def __init__(self, nodes, selector=None, filters=None):
        self.nodes = list(nodes)
        self.selector = selector or ""
        self.filters = list(filters or [])

    def filter(self, has_text=None, has=None):
        filters = list(self.filters)
        if has_text:
            filters.append(str(has_text))
        return FakeLocator(self.nodes, self.selector, filters)

    @property
    def first(self):
        return self

    async def count(self):
        nodes = self.nodes
        if "comment-1" in self.selector:
            nodes = [node for node in nodes if node["comment_id"] == "comment-1"]
        elif "duplicate" in self.selector:
            nodes = [node for node in nodes if node["comment_id"] == "duplicate"]
        for needle in self.filters:
            nodes = [
                node
                for node in nodes
                if needle in node["author_name"] or needle in node["comment_text"]
            ]
        return len(nodes)


class FakeLocatorPage:
    def __init__(self, nodes):
        self.nodes = nodes

    def locator(self, selector):
        return FakeLocator(self.nodes, selector)


def test_locate_comment_node_by_comment_id():
    page = FakeLocatorPage(
        [
            {"comment_id": "comment-1", "author_name": "Alice", "comment_text": "How much?"},
            {"comment_id": "comment-2", "author_name": "Bob", "comment_text": "PM"},
        ]
    )

    result = asyncio.run(locate_comment_node(page, comment_id="comment-1"))

    assert result.diagnostics == {
        "found": True,
        "strategy": "comment_id",
        "matched_count": 1,
        "ambiguous": False,
    }


def test_locate_comment_node_author_text_fallback():
    page = FakeLocatorPage(
        [
            {"comment_id": "comment-1", "author_name": "Alice", "comment_text": "How much?"},
            {"comment_id": "comment-2", "author_name": "Bob", "comment_text": "PM please"},
        ]
    )

    result = asyncio.run(locate_comment_node(page, author_name="Bob", comment_text="PM please"))

    assert result.diagnostics["found"] is True
    assert result.diagnostics["strategy"] == "author_text"
    assert result.diagnostics["matched_count"] == 1


def test_locate_comment_node_reports_ambiguous_matches():
    page = FakeLocatorPage(
        [
            {"comment_id": "duplicate", "author_name": "Alice", "comment_text": "How much?"},
            {"comment_id": "duplicate", "author_name": "Alice", "comment_text": "How much?"},
        ]
    )

    result = asyncio.run(locate_comment_node(page, comment_id="duplicate"))

    assert result.diagnostics["found"] is False
    assert result.diagnostics["ambiguous"] is True
    assert result.diagnostics["matched_count"] == 2
