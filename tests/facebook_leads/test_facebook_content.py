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
