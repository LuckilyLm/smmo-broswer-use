import asyncio

from src.facebook_leads.facebook.login_state import detect_login_state


class FakeLocator:
    def __init__(self, count=0, text=""):
        self._count = count
        self._text = text

    async def count(self):
        return self._count

    async def inner_text(self, timeout=None):
        return self._text


class FakePage:
    def __init__(self, url, title="", body="", selector_counts=None):
        self.url = url
        self._title = title
        self._body = body
        self.selector_counts = selector_counts or {}

    async def title(self):
        return self._title

    def locator(self, selector):
        if selector == "body":
            return FakeLocator(text=self._body)
        return FakeLocator(count=self.selector_counts.get(selector, 0))


def test_detects_logged_in():
    page = FakePage("https://www.facebook.com/", "Facebook", "Home Watch Notifications")

    assert asyncio.run(detect_login_state(page)) == "logged_in"


def test_detects_logged_out():
    page = FakePage(
        "https://www.facebook.com/login/",
        "Facebook log in",
        "Log into Facebook",
        {"input[name='email']": 1},
    )

    assert asyncio.run(detect_login_state(page)) == "logged_out"


def test_detects_checkpoint():
    page = FakePage("https://www.facebook.com/checkpoint/123", "Facebook", "")

    assert asyncio.run(detect_login_state(page)) == "checkpoint"


def test_detects_captcha():
    page = FakePage("https://www.facebook.com/", "Facebook", "Security check captcha")

    assert asyncio.run(detect_login_state(page)) == "captcha"


def test_detects_unknown():
    page = FakePage("https://example.com/", "Example", "Hello")

    assert asyncio.run(detect_login_state(page)) == "unknown"

