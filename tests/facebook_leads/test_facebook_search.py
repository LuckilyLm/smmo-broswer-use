import asyncio

from src.facebook_leads.facebook.search import (
    build_facebook_search_url,
    classify_facebook_content_url,
    discover_content_candidates,
    is_candidate_content_url,
    normalize_facebook_url,
    search_facebook_contents,
)


class FakePage:
    def __init__(self, batches):
        self.batches = batches
        self.scrolls = 0
        self.goto_calls = []
        self.url = "https://www.facebook.com/"

    @property
    def anchor_records(self):
        index = min(self.scrolls, len(self.batches) - 1)
        return self.batches[index]

    async def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))
        self.url = url

    async def scroll_once(self):
        self.scrolls += 1


class DelayedAnchorPage(FakePage):
    def __init__(self, batches):
        super().__init__(batches)
        self.waits = 0

    @property
    def anchor_records(self):
        index = min(self.waits, len(self.batches) - 1)
        return self.batches[index]

    async def wait_for_timeout(self, ms):
        self.waits += 1


def test_facebook_url_classification_covers_common_formats():
    cases = {
        "https://www.facebook.com/a/posts/123?x=1": "post",
        "https://www.facebook.com/reel/123/": "reel",
        "https://www.facebook.com/reels/123/": "reel",
        "https://www.facebook.com/a/videos/123/": "video",
        "https://www.facebook.com/permalink.php?story_fbid=1&id=2": "post",
        "https://www.facebook.com/story.php?story_fbid=1&id=2": "post",
    }

    for url, expected in cases.items():
        normalized = normalize_facebook_url(url)
        assert normalized is not None
        assert classify_facebook_content_url(normalized) == expected
        assert is_candidate_content_url(normalized)


def test_non_facebook_url_is_not_candidate():
    assert normalize_facebook_url("https://example.com/posts/1") is None
    assert not is_candidate_content_url("https://example.com/posts/1")
    assert not is_candidate_content_url("https://www.facebook.com/login_alerts/start?fbid=1")


def test_search_url_encodes_keyword():
    assert build_facebook_search_url("car detailing") == (
        "https://www.facebook.com/search/top/?q=car+detailing"
    )


def test_content_url_dedupe_and_limit():
    page = FakePage(
        [[
            {"href": "https://www.facebook.com/a/posts/1?tracking=drop", "text": "First"},
            {"href": "https://www.facebook.com/a/posts/1", "text": "Duplicate"},
            {"href": "https://www.facebook.com/reel/2", "text": "Second"},
        ]]
    )

    result = asyncio.run(discover_content_candidates(page, limit=1, max_scrolls=0))

    assert len(result) == 1
    assert result[0].url == "https://www.facebook.com/a/posts/1"


def test_search_skips_notification_noise_anchors():
    page = FakePage(
        [[
            {
                "href": "https://www.facebook.com/groups/1/posts/2",
                "text": "未读Alice 赞了你的评论",
            },
            {"href": "https://www.facebook.com/reel/3", "text": "car detailing"},
        ]]
    )

    result = asyncio.run(discover_content_candidates(page, limit=2, max_scrolls=0))

    assert [item.url for item in result] == ["https://www.facebook.com/reel/3"]


def test_search_result_limit_and_navigation():
    page = FakePage(
        [[
            {"href": f"https://www.facebook.com/a/posts/{number}", "text": str(number)}
            for number in range(5)
        ]]
    )

    result = asyncio.run(search_facebook_contents(page, "car detailing", limit=3, max_scrolls=0))

    assert len(result) == 3
    assert page.goto_calls[0][0] == "https://www.facebook.com/search/top/?q=car+detailing"


def test_search_waits_for_delayed_candidate_anchors():
    page = DelayedAnchorPage(
        [
            [],
            [],
            [
                {
                    "href": (
                        "https://www.facebook.com/reel/1350756286507291/"
                        "?__cft__[0]=drop&__tn__=%2CO%2CP-R"
                    ),
                    "text": "3天",
                }
            ],
        ]
    )

    result = asyncio.run(search_facebook_contents(page, "car detailing", limit=1, max_scrolls=0))

    assert len(result) == 1
    assert result[0].url == "https://www.facebook.com/reel/1350756286507291"
    assert page.waits == 2


def test_max_scrolls_is_respected():
    page = FakePage(
        [
            [],
            [{"href": "https://www.facebook.com/a/posts/1", "text": "First"}],
            [{"href": "https://www.facebook.com/a/posts/2", "text": "Second"}],
        ]
    )

    result = asyncio.run(discover_content_candidates(page, limit=10, max_scrolls=1))

    assert [item.url for item in result] == ["https://www.facebook.com/a/posts/1"]
    assert page.scrolls == 1
