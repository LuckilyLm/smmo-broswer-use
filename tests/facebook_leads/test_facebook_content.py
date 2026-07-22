import asyncio

from src.facebook_leads.facebook.content import open_content


class FakePage:
    def __init__(self):
        self.goto_calls = []
        self.wait_calls = []
        self.timeout_calls = []
        self.url = "https://www.facebook.com/search/top/?q=x"
        self.content_ready_summary = {
            "body_present": True,
            "is_search_page": False,
            "has_reel_viewer": True,
            "has_post_article": False,
            "comment_button_count": 1,
        }

    async def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))
        self.url = "https://www.facebook.com/reel/final"

    async def wait_for_load_state(self, state, timeout=None):
        self.wait_calls.append((state, timeout))

    async def wait_for_timeout(self, ms):
        self.timeout_calls.append(ms)


def test_open_content_uses_current_page_goto_only():
    page = FakePage()

    result = asyncio.run(open_content(page, "https://www.facebook.com/a/posts/1"))

    assert page.goto_calls == [
        (
            "https://www.facebook.com/a/posts/1",
            {"wait_until": "domcontentloaded", "timeout": 30000},
        )
    ]
    assert page.wait_calls == [("networkidle", 5000)]
    assert result["requested_url"] == "https://www.facebook.com/a/posts/1"
    assert result["final_url"] == "https://www.facebook.com/reel/final"
    assert result["redirected"] is True


class TimeoutReadyPage(FakePage):
    async def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))
        self.url = url
        raise TimeoutError("Page.goto: Timeout 30000ms exceeded")


def test_open_content_treats_timeout_with_ready_page_as_degraded_success():
    page = TimeoutReadyPage()

    result = asyncio.run(open_content(page, "https://www.facebook.com/permalink.php?story_fbid=1"))

    assert len(page.goto_calls) == 1
    assert result["navigation_status"] == "navigation_degraded_success"
    assert result["attempt_count"] == 1


class TimeoutNotReadyPage(FakePage):
    def __init__(self):
        super().__init__()
        self.content_ready_summary = {
            "body_present": False,
            "is_search_page": False,
            "has_reel_viewer": False,
            "has_post_article": False,
            "comment_button_count": 0,
        }

    async def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))
        self.url = url
        raise TimeoutError("Page.goto: Timeout 30000ms exceeded")


def test_open_content_retries_timeout_before_raising():
    page = TimeoutNotReadyPage()

    try:
        asyncio.run(open_content(page, "https://www.facebook.com/permalink.php?story_fbid=1"))
    except TimeoutError:
        pass

    assert len(page.goto_calls) == 2
