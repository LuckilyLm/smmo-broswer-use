import asyncio
import json
from pathlib import Path

import src.facebook_leads.facebook.scanner as scanner
from src.facebook_leads.facebook.models import FacebookComment, FacebookContentCandidate
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

    async def evaluate(self, script):
        return {
            "url": self.url,
            "title": "Facebook",
            "body_present": True,
            "is_search_page": False,
            "has_reel_viewer": False,
            "has_post_article": True,
            "comment_button_count": 1,
        }


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


class FakeRootResult:
    def __init__(self):
        self.root = object()
        self.root_type = "article"


def install_scan_fakes(monkeypatch, *, candidates, open_content):
    async def fake_search(page, keyword, limit, max_scrolls):
        return candidates

    async def fake_metadata(page, candidate):
        return candidate, {"final_url": candidate.url, "text_preview": "massage chair", "author_name": "Shop"}

    async def fake_find_root(page):
        return FakeRootResult()

    async def fake_count(root):
        return 1

    async def fake_expand(page, max_expand_clicks):
        return {"comment_panel": {"elapsed_ms": 0, "after": {"count": 1}}, "comment_root_type": "article"}

    async def fake_wait(page, timeout_ms, min_count):
        return 1

    async def fake_extract(page, source_content_url, root, limit):
        return [
            FacebookComment(
                comment_id=source_content_url.rsplit("/", 1)[-1],
                author_name="Buyer",
                author_url=None,
                text="Still available?",
                timestamp_text=None,
                comment_url=None,
                is_reply=False,
                parent_comment_id=None,
                source_content_url=source_content_url,
                fingerprint=f"fp-{source_content_url}",
            )
        ]

    monkeypatch.setattr(scanner, "search_facebook_contents", fake_search)
    monkeypatch.setattr(scanner, "open_content", open_content)
    monkeypatch.setattr(scanner, "extract_content_metadata", fake_metadata)
    monkeypatch.setattr(scanner, "find_comment_root", fake_find_root)
    monkeypatch.setattr(scanner, "count_comment_candidates", fake_count)
    monkeypatch.setattr(scanner, "expand_comments", fake_expand)
    monkeypatch.setattr(scanner, "wait_for_comments_loaded", fake_wait)
    monkeypatch.setattr(scanner, "extract_comments", fake_extract)


def test_content_timeout_records_failure_and_continues(monkeypatch, tmp_path):
    candidates = [
        FacebookContentCandidate(url="https://www.facebook.com/posts/1", content_type="post"),
        FacebookContentCandidate(url="https://www.facebook.com/posts/2", content_type="post"),
    ]
    calls = {"count": 0}

    async def fake_open(page, url):
        calls["count"] += 1
        if url.endswith("/1"):
            raise TimeoutError("Page.goto: Timeout 30000ms exceeded")
        return {"final_url": url, "retry_count": 0}

    install_scan_fakes(monkeypatch, candidates=candidates, open_content=fake_open)
    output = tmp_path / "scan_result.json"

    result = asyncio.run(run_readonly_scan(FakePage(), "massage chair", incremental_output_path=output))
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert result.success is True
    assert result.status == "partial"
    assert result.content_success_count == 1
    assert result.content_failure_count == 1
    assert result.comments[0].source_content_url.endswith("/2")
    assert payload["content_failure_count"] == 1
    assert payload["diagnostics"]["content_failures"][0]["stage"] == "content_open"


def test_browser_disconnect_is_fatal(monkeypatch):
    candidates = [FacebookContentCandidate(url="https://www.facebook.com/posts/1", content_type="post")]

    async def fake_open(page, url):
        raise ConnectionError("browser disconnected")

    install_scan_fakes(monkeypatch, candidates=candidates, open_content=fake_open)

    result = asyncio.run(run_readonly_scan(FakePage(), "massage chair"))

    assert result.success is False
    assert result.status == "failed"
    assert result.error_type == "ConnectionError"


def test_resume_skips_successful_content_and_deduplicates_comments(monkeypatch):
    candidates = [
        FacebookContentCandidate(url="https://www.facebook.com/posts/1", content_type="post"),
        FacebookContentCandidate(url="https://www.facebook.com/posts/2", content_type="post"),
    ]
    resume_payload = {
        "contents": [candidates[0].to_dict()],
        "comments": [
            FacebookComment(
                comment_id="1",
                author_name="Buyer",
                author_url=None,
                text="Location?",
                timestamp_text=None,
                comment_url=None,
                is_reply=False,
                parent_comment_id=None,
                source_content_url="https://www.facebook.com/posts/1",
                fingerprint="fp-existing",
            ).to_dict()
        ],
        "diagnostics": {"per_content": [{"discovered_url": "https://www.facebook.com/posts/1"}]},
    }

    async def fake_open(page, url):
        return {"final_url": url}

    install_scan_fakes(monkeypatch, candidates=candidates, open_content=fake_open)

    result = asyncio.run(run_readonly_scan(FakePage(), "massage chair", resume_payload=resume_payload))

    assert result.success is True
    assert result.status == "completed"
    assert result.diagnostics["resume_skipped_success_count"] == 1
    assert len(result.comments) == 2
    assert [comment.source_content_url for comment in result.comments] == [
        "https://www.facebook.com/posts/1",
        "https://www.facebook.com/posts/2",
    ]
