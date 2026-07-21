import asyncio
from pathlib import Path

from src.facebook_leads.facebook.scanner import run_readonly_scan


class FakeLocator:
    def __init__(self, count=0, text=""):
        self._count = count
        self._text = text

    async def count(self):
        return self._count

    async def inner_text(self, timeout=None):
        return self._text


class FakeButton:
    def __init__(self, page):
        self.page = page

    async def click(self, timeout=None):
        self.page.comment_dom_count += 1


class FakePage:
    def __init__(self, url="https://www.facebook.com/a/posts/1", body="Home Watch"):
        self.url = url
        self.body = body
        self.goto_calls = []
        self.anchor_records = []
        self.comment_records = []
        self.comment_dom_count = 0
        self.buttons = []

    async def title(self):
        return "Facebook"

    def locator(self, selector):
        if selector == "body":
            return FakeLocator(text=self.body)
        return FakeLocator(count=0)

    async def goto(self, url, **kwargs):
        self.goto_calls.append(url)
        self.url = url

    async def scroll_once(self):
        return None

    async def next_more_comments_button(self):
        if self.buttons:
            return self.buttons.pop(0)
        return None

    async def wait_for_timeout(self, ms):
        return None

    async def wait_for_load_state(self, *args, **kwargs):
        return None


def test_current_page_only_does_not_execute_search():
    page = FakePage()
    page.comment_records = [
        {
            "comment_id": "1",
            "author_name": "Alice",
            "author_url": None,
            "text": "Interested",
            "timestamp_text": None,
            "comment_url": None,
            "is_reply": False,
            "parent_comment_id": None,
        }
    ]

    result = asyncio.run(run_readonly_scan(page, None, current_page_only=True))

    assert result.success is True
    assert page.goto_calls == []
    assert len(result.comments) == 1


def test_current_page_only_uses_active_page_url_not_internal_links():
    page = FakePage(url="https://www.facebook.com/reel/935673319498158")
    page.anchor_records = [
        {"href": "https://www.facebook.com/reel/following", "text": "Following"},
    ]
    page.comment_records = [
        {
            "comment_id": "1",
            "author_name": "Alice",
            "author_url": None,
            "text": "Interested",
            "timestamp_text": None,
            "comment_url": None,
            "is_reply": False,
            "parent_comment_id": None,
        }
    ]

    result = asyncio.run(run_readonly_scan(page, None, current_page_only=True))

    assert result.success is True
    assert result.contents[0].url == "https://www.facebook.com/reel/935673319498158"
    assert result.comments[0].source_content_url == "https://www.facebook.com/reel/935673319498158"
    assert page.goto_calls == []


def test_current_page_only_requires_facebook_content_page():
    page = FakePage(url="https://www.facebook.com/", body="Home Watch Notifications")

    result = asyncio.run(run_readonly_scan(page, None, current_page_only=True))

    assert result.success is False
    assert result.stage == "not_facebook_content_page"
    assert page.goto_calls == []


def test_logged_out_stops_before_search():
    page = FakePage(url="https://www.facebook.com/login/", body="Log into Facebook")

    result = asyncio.run(run_readonly_scan(page, "car detailing"))

    assert result.success is False
    assert result.stage == "stopped_login_state"
    assert result.login_state == "logged_out"
    assert page.goto_calls == []


def test_checkpoint_stops_before_search():
    page = FakePage(url="https://www.facebook.com/checkpoint/123")

    result = asyncio.run(run_readonly_scan(page, "car detailing"))

    assert result.success is False
    assert result.login_state == "checkpoint"
    assert page.goto_calls == []


def test_captcha_stops_before_search():
    page = FakePage(body="Security check captcha")

    result = asyncio.run(run_readonly_scan(page, "car detailing"))

    assert result.success is False
    assert result.login_state == "captcha"
    assert page.goto_calls == []


def test_scanner_does_not_import_agent_llm_or_write_actions():
    project_root = Path(__file__).parents[2]
    scanner_source = (project_root / "src/facebook_leads/facebook/scanner.py").read_text(
        encoding="utf-8"
    )
    forbidden = [
        "BrowserUseAgent",
        "get_llm_model",
        ".fill(",
        "keyboard.type",
        "reply(",
        "like(",
        "message(",
        "follow(",
        ".close(",
    ]

    for snippet in forbidden:
        assert snippet not in scanner_source
