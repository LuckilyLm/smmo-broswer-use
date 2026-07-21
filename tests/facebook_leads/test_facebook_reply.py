import asyncio
import json
from pathlib import Path

from src.facebook_leads.facebook.comments import CommentNodeLocation
from src.facebook_leads.facebook.reply import (
    LocatorSearchResult,
    ReplyRequest,
    append_reply_history,
    find_reply_action,
    find_reply_input,
    find_successful_duplicate,
    reply_to_comment,
    verify_reply_sent,
)


class FakeLocator:
    def __init__(self, count=1, text="", label=None):
        self._count = count
        self.text = text
        self.label = label
        self.clicked = False
        self.filled_values = []
        self.inner_locators = {}

    @property
    def first(self):
        return self

    async def count(self):
        return self._count

    async def click(self, timeout=None):
        self.clicked = True

    async def fill(self, value):
        self.text = value
        self.filled_values.append(value)

    async def input_value(self, timeout=None):
        return self.text

    async def inner_text(self, timeout=None):
        return self.text

    def locator(self, selector):
        return self.inner_locators.get(selector, FakeLocator(0))

    def get_by_role(self, role, name=None):
        return self.inner_locators.get((role, str(getattr(name, "pattern", name))), FakeLocator(0))

    def filter(self, has_text=None, has=None):
        return self


class FakeCommentNode(FakeLocator):
    def __init__(self, reply_count=1):
        super().__init__(1)
        self.reply_locator = FakeLocator(reply_count, label="Reply")

    async def find_reply_action(self):
        locator = self.reply_locator if self.reply_locator._count == 1 else None
        return LocatorSearchResult(locator, "fake_reply", self.reply_locator._count)


class FakePage:
    def __init__(
        self,
        *,
        locate_count=1,
        reply_count=1,
        input_count=1,
        send_count=1,
        verification=None,
        login_text="Home",
        url="https://www.facebook.com/reel/1",
    ):
        self.url = url
        self.comment_node = FakeCommentNode(reply_count=reply_count)
        self.input_locator = FakeLocator(input_count)
        self.send_locator = FakeLocator(send_count, label="Send")
        self.locate_count = locate_count
        self.verification = verification
        self.login_text = login_text
        self.goto_urls = []
        self.snapshots = [[], ["reply-box"]]
        self.closed = False

    async def goto(self, url, wait_until=None, timeout=None):
        self.url = url
        self.goto_urls.append(url)

    async def wait_for_timeout(self, ms):
        return None

    async def locate_comment_node(self, **kwargs):
        return CommentNodeLocation(
            locator=self.comment_node if self.locate_count == 1 else None,
            diagnostics={
                "found": self.locate_count == 1,
                "strategy": "fake",
                "matched_count": self.locate_count,
                "ambiguous": self.locate_count > 1,
            },
        )

    async def snapshot_visible_textboxes(self):
        return self.snapshots.pop(0) if self.snapshots else ["reply-box"]

    async def find_reply_input(self, comment_node, before_snapshot):
        locator = self.input_locator if self.input_locator._count == 1 else None
        return LocatorSearchResult(locator, "fake_input", self.input_locator._count)

    async def find_send_action(self, input_locator):
        locator = self.send_locator if self.send_locator._count == 1 else None
        return LocatorSearchResult(locator, "fake_send", self.send_locator._count)

    async def verify_reply_sent(self, request, input_locator):
        return self.verification or {"verified": True, "strategy": "fake", "evidence": {"visible": True}}

    async def title(self):
        return "Facebook"

    def locator(self, selector):
        if selector == "body":
            return FakeLocator(1, text=self.login_text)
        if selector == "[role='textbox']:focus, textarea:focus, [contenteditable='true']:focus":
            return FakeLocator(0)
        return FakeLocator(0)


def request(**kwargs):
    data = {
        "source_content_url": "https://www.facebook.com/reel/1",
        "direct_comment_url": "https://www.facebook.com/reel/1?comment_id=c1",
        "comment_id": "c1",
        "author_name": "Alice",
        "comment_text": "How much?",
        "fingerprint": "fp1",
        "reply_text": "Hello",
    }
    data.update(kwargs)
    return ReplyRequest(**data)


def run(page, req, tmp_path):
    return asyncio.run(
        reply_to_comment(
            page,
            req,
            artifacts_dir=tmp_path / "replies",
            history_path=tmp_path / "history.jsonl",
        )
    )


def test_reply_dry_run_fills_but_does_not_send_and_clears_by_default(tmp_path):
    page = FakePage()

    payload = run(page, request(), tmp_path)
    result = payload["result"]

    assert result["success"] is True
    assert result["stage"] == "dry_run_complete"
    assert result["located"] is True
    assert result["matched_count"] == 1
    assert result["reply_clicked"] is True
    assert result["input_found"] is True
    assert result["text_filled"] is True
    assert result["sent"] is False
    assert result["dry_run"] is True
    assert page.input_locator.filled_values == ["Hello", ""]
    assert not (tmp_path / "history.jsonl").exists()


def test_dry_run_keep_filled_preserves_text(tmp_path):
    page = FakePage()

    run(page, request(keep_filled=True), tmp_path)

    assert page.input_locator.filled_values == ["Hello"]


def test_zero_match_blocks_reply(tmp_path):
    page = FakePage(locate_count=0)

    payload = run(page, request(), tmp_path)

    assert payload["result"]["success"] is False
    assert payload["result"]["stage"] == "locate_comment"
    assert page.comment_node.reply_locator.clicked is False


def test_multiple_matches_blocks_reply_as_ambiguous(tmp_path):
    page = FakePage(locate_count=2)

    payload = run(page, request(), tmp_path)

    assert payload["result"]["success"] is False
    assert payload["result"]["diagnostics"]["ambiguous"] is True
    assert page.comment_node.reply_locator.clicked is False


def test_reply_action_must_be_unique_inside_comment_node(tmp_path):
    page = FakePage(reply_count=0)

    payload = run(page, request(), tmp_path)

    assert payload["result"]["stage"] == "find_reply_action"
    assert payload["result"]["reply_clicked"] is False


def test_reply_action_supports_multilingual_fake_node():
    node = FakeCommentNode(reply_count=1)
    node.reply_locator.label = "回复"

    result = asyncio.run(find_reply_action(node))

    assert result.matched_count == 1
    assert result.locator is node.reply_locator


def test_find_reply_input_uses_added_or_active_composer_not_main_comment_box():
    page = FakePage(input_count=1)
    before = []

    result = asyncio.run(find_reply_input(page, page.comment_node, before))

    assert result.matched_count == 1
    assert result.locator is page.input_locator


def test_confirm_send_false_does_not_send(tmp_path):
    page = FakePage()

    run(page, request(confirm_send=False), tmp_path)

    assert page.send_locator.clicked is False


def test_confirm_send_without_yes_still_dry_runs(tmp_path):
    page = FakePage()

    payload = run(page, request(confirm_send=True, yes=False), tmp_path)

    assert payload["result"]["dry_run"] is True
    assert payload["result"]["sent"] is False
    assert "真实发送需要同时提供 --confirm-send --yes" in payload["diagnostics"]["send_gate"]


def test_confirm_send_with_yes_sends_and_writes_history(tmp_path):
    page = FakePage()

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["sent"] is True
    assert page.send_locator.clicked is True
    history = (tmp_path / "history.jsonl").read_text(encoding="utf-8")
    assert '"comment_id": "c1"' in history


def test_send_blocks_if_input_text_changes(tmp_path):
    page = FakePage()
    original_fill = page.input_locator.fill

    async def fill_wrong(value):
        await original_fill("Wrong")

    page.input_locator.fill = fill_wrong

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["stage"] == "fill_reply_input"
    assert page.send_locator.clicked is False


def test_checkpoint_and_captcha_block_send(tmp_path):
    checkpoint = run(
        FakePage(url="https://www.facebook.com/checkpoint/"),
        request(confirm_send=True, yes=True, direct_comment_url="https://www.facebook.com/checkpoint/"),
        tmp_path / "a",
    )
    captcha = run(FakePage(login_text="captcha"), request(confirm_send=True, yes=True), tmp_path / "b")

    assert checkpoint["result"]["stage"] == "pre_send_safety"
    assert captcha["result"]["stage"] == "pre_send_safety"


def test_duplicate_reply_default_refuses_and_allow_duplicate_overrides(tmp_path):
    history_path = tmp_path / "history.jsonl"
    append_reply_history(history_path, request(), verified=True)
    duplicate = find_successful_duplicate(history_path, comment_id="c1", fingerprint=None)

    assert duplicate["comment_id"] == "c1"
    refused = asyncio.run(
        reply_to_comment(FakePage(), request(confirm_send=True, yes=True), artifacts_dir=tmp_path / "r1", history_path=history_path)
    )
    allowed = asyncio.run(
        reply_to_comment(
            FakePage(),
            request(confirm_send=True, yes=True, allow_duplicate=True),
            artifacts_dir=tmp_path / "r2",
            history_path=history_path,
        )
    )
    assert refused["result"]["stage"] == "duplicate_check"
    assert allowed["result"]["sent"] is True


def test_duplicate_history_does_not_block_dry_run(tmp_path):
    history_path = tmp_path / "history.jsonl"
    append_reply_history(history_path, request(), verified=True)

    payload = asyncio.run(
        reply_to_comment(FakePage(), request(), artifacts_dir=tmp_path / "replies", history_path=history_path)
    )

    assert payload["result"]["stage"] == "dry_run_complete"
    assert payload["result"]["sent"] is False


def test_verify_reply_sent_can_be_unconfirmed():
    page = FakePage(verification={"verified": False, "strategy": "unconfirmed", "evidence": {}})

    result = asyncio.run(verify_reply_sent(page, request(), page.input_locator))

    assert result["verified"] is False


def test_reply_result_json_is_written_without_history_for_dry_run(tmp_path):
    payload = run(FakePage(), request(), tmp_path)
    result_path = Path(payload["paths"]["reply_result_json"])
    data = json.loads(result_path.read_text(encoding="utf-8"))

    assert data["request"]["comment_id"] == "c1"
    assert data["result"]["sent"] is False
    assert not (tmp_path / "history.jsonl").exists()


def test_reply_source_has_no_llm_agent_or_remote_browser_close():
    project_root = Path(__file__).parents[2]
    source = (project_root / "src/facebook_leads/facebook/reply.py").read_text(encoding="utf-8")
    cli_source = (project_root / "scripts/facebook_reply_one.py").read_text(encoding="utf-8")
    combined = "\n".join([source, cli_source])

    for forbidden in ["BrowserUseAgent", "get_llm_model", "browser.close(", "context.close("]:
        assert forbidden not in combined
