import asyncio
from pathlib import Path

import pytest

from src.facebook_leads.browser_adapter import (
    BrowserCdpNotConfiguredError,
    get_active_page,
    require_browser_cdp,
    select_active_or_facebook_page,
    summarize_pages,
    verify_page_primitives,
)


class FakePage:
    def __init__(self, url: str, title: str = "Title", closed: bool = False):
        self.url = url
        self._title = title
        self._closed = closed
        self.goto_calls: list[str] = []

    async def title(self):
        return self._title

    def locator(self, selector):
        assert selector == "body"
        return self

    async def count(self):
        return 1

    async def goto(self, url):
        self.goto_calls.append(url)
        self.url = url

    def is_closed(self):
        return self._closed


class FakeSession:
    def __init__(self, pages):
        self.context = type("Context", (), {"pages": pages})()


class FakeBrowserContext:
    def __init__(self, pages, active_page):
        self.pages = pages
        self.active_page = active_page
        self.agent_accessor_calls = 0

    async def get_agent_current_page(self):
        self.agent_accessor_calls += 1
        return self.active_page

    async def get_session(self):
        return FakeSession(self.pages)


def test_browser_cdp_missing_raises_clear_error():
    with pytest.raises(BrowserCdpNotConfiguredError, match="BROWSER_CDP"):
        require_browser_cdp({})


def test_browser_cdp_is_read_from_environment_mapping():
    assert require_browser_cdp({"BROWSER_CDP": "http://host:9222"}) == "http://host:9222"


def test_page_accessor_is_wrapped_behind_adapter():
    page = FakePage("https://example.test")
    context = FakeBrowserContext([page], page)

    assert asyncio.run(get_active_page(context)) is page
    assert context.agent_accessor_calls == 1


def test_multiple_pages_are_observable_without_choosing_pages_last_blindly():
    first = FakePage("https://first.example")
    second = FakePage("about:blank", closed=True)
    context = FakeBrowserContext([first, second], first)

    summaries = asyncio.run(summarize_pages(context))

    assert [summary.url for summary in summaries] == ["https://first.example", "about:blank"]
    assert [summary.is_closed for summary in summaries] == [False, True]


def test_select_active_or_facebook_page_prefers_current_facebook_page():
    facebook_page = FakePage("https://www.facebook.com/reel/123")
    other_page = FakePage("https://example.com")
    context = FakeBrowserContext([facebook_page, other_page], facebook_page)

    assert asyncio.run(select_active_or_facebook_page(context)) is facebook_page


def test_select_active_or_facebook_page_falls_back_to_content_page():
    active_page = FakePage("https://example.com")
    facebook_home = FakePage("https://www.facebook.com/")
    facebook_content = FakePage("https://www.facebook.com/reel/123")
    context = FakeBrowserContext([active_page, facebook_home, facebook_content], active_page)

    assert asyncio.run(select_active_or_facebook_page(context)) is facebook_content


def test_select_active_or_facebook_page_falls_back_to_any_facebook_page():
    active_page = FakePage("https://example.com")
    facebook_home = FakePage("https://www.facebook.com/")
    context = FakeBrowserContext([active_page, facebook_home], active_page)

    assert asyncio.run(select_active_or_facebook_page(context)) is facebook_home


def test_page_primitives_support_title_locator_and_optional_goto():
    page = FakePage("https://start.example", title="Start")

    result = asyncio.run(verify_page_primitives(page, goto_url="https://example.com"))

    assert result["url_before"] == "https://start.example"
    assert result["title_before"] == "Start"
    assert result["body_count_before"] == 1
    assert result["url_after"] == "https://example.com"
    assert result["body_count_after"] == 1
    assert page.goto_calls == ["https://example.com"]


def test_business_code_does_not_depend_on_browser_use_private_page_fields():
    project_root = Path(__file__).parents[2]
    business_paths = [
        path
        for path in (project_root / "src/facebook_leads").glob("*.py")
        if path.name != "browser_adapter.py"
    ]
    forbidden_snippets = [
        "agent_current_page",
        "human_current_page",
        "session.context",
        "get_session(",
        "_initialize_session",
    ]

    for path in business_paths:
        source = path.read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            assert snippet not in source


def test_adapter_and_spike_script_contain_no_facebook_business_logic():
    project_root = Path(__file__).parents[2]
    paths = [
        project_root / "src/facebook_leads/browser_adapter.py",
        project_root / "scripts/browser_integration_spike.py",
    ]
    forbidden_snippets = [
        "comment",
        "reply",
        "search_posts",
        "get_comments",
        "analyze_batch",
        "BrowserUseAgent",
    ]

    for path in paths:
        source = path.read_text(encoding="utf-8").lower()
        for snippet in forbidden_snippets:
            assert snippet.lower() not in source
