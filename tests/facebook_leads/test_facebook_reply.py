import asyncio
import inspect
import json
from pathlib import Path

from src.facebook_leads.facebook.comments import CommentNodeLocation
from src.facebook_leads.facebook.reply import (
    LocatorSearchResult,
    ReplyComposerSearchResult,
    ReplyRequest,
    append_reply_history,
    build_reply_idempotency_key,
    click_reply_action_with_recovery,
    find_reply_composer,
    find_reply_action,
    find_reply_input,
    find_send_action,
    find_successful_duplicate,
    reply_to_comment,
    verify_reply_sent,
)


class FakeLocator:
    def __init__(self, count=1, text="", label=None, click_exc=None, click_excs=None, visible=True):
        self._count = count
        self.text = text
        self.label = label
        self.click_exc = click_exc
        self.click_excs = list(click_excs or [])
        self.visible = visible
        self.clicked = False
        self.click_count = 0
        self.filled_values = []
        self.inner_locators = {}
        self.contains_input_result = True
        self.scroll_count = 0

    @property
    def first(self):
        return self

    async def count(self):
        return self._count

    async def click(self, timeout=None):
        if self.click_excs:
            exc = self.click_excs.pop(0)
            if exc:
                raise exc
        if self.click_exc:
            raise self.click_exc
        self.clicked = True
        self.click_count += 1

    async def scroll_into_view_if_needed(self, timeout=None):
        self.scroll_count += 1

    async def fill(self, value):
        self.text = value
        self.filled_values.append(value)

    async def input_value(self, timeout=None):
        return self.text

    async def inner_text(self, timeout=None):
        return self.text

    async def is_visible(self, timeout=None):
        return self.visible

    async def contains_input(self, input_locator):
        return self.contains_input_result

    def locator(self, selector):
        return self.inner_locators.get(selector, FakeLocator(0))

    def get_by_role(self, role, name=None):
        return self.inner_locators.get((role, str(getattr(name, "pattern", name))), FakeLocator(0))

    def filter(self, has_text=None, has=None):
        return self


class FakeCommentNode(FakeLocator):
    def __init__(self, reply_count=1, reply_click_excs=None):
        super().__init__(1)
        self.reply_locator = FakeLocator(reply_count, label="Reply", click_excs=reply_click_excs)

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
        composer_count=1,
        composer_send_count=None,
        verification=None,
        login_text="Home",
        url="https://www.facebook.com/reel/1",
        existing_reply=False,
        send_click_exc=None,
        reply_click_excs=None,
        input_counts=None,
        obstruction=None,
        dismiss_result=None,
        verify_exc=None,
    ):
        self.url = url
        self.comment_node = FakeCommentNode(reply_count=reply_count, reply_click_excs=reply_click_excs)
        self.input_locator = FakeLocator(input_count)
        self.composer_locator = FakeLocator(composer_count, label="composer")
        self.composer_send_locator = FakeLocator(
            send_count if composer_send_count is None else composer_send_count,
            label="Composer Send",
            click_exc=send_click_exc,
        )
        self.send_locator = self.composer_send_locator
        self.global_send_locator = FakeLocator(send_count, label="Global Send", click_exc=send_click_exc)
        self.locate_count = locate_count
        self.verification = verification
        self.login_text = login_text
        self.goto_urls = []
        self.snapshots = [[], ["reply-box"]]
        self.closed = False
        self.existing_reply = existing_reply
        self.verify_exc = verify_exc
        self.locate_calls = 0
        self.input_counts = list(input_counts or [])
        self.obstruction = obstruction or {"obstruction_found": False, "obstruction_types": [], "dismissable_count": 0, "diagnostics": []}
        self.dismiss_result = dismiss_result or {"dismissed_count": 0, "attempts": []}
        self.dismiss_calls = 0

    async def goto(self, url, wait_until=None, timeout=None):
        self.url = url
        self.goto_urls.append(url)

    async def wait_for_timeout(self, ms):
        return None

    async def locate_comment_node(self, **kwargs):
        self.locate_calls += 1
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
        count = self.input_counts.pop(0) if self.input_counts else self.input_locator._count
        locator = self.input_locator if count == 1 else None
        return LocatorSearchResult(locator, "fake_input", count)

    async def detect_page_obstructions(self, target=None):
        return self.obstruction

    async def dismiss_safe_obstructions(self, max_attempts=3):
        self.dismiss_calls += 1
        return self.dismiss_result

    async def find_reply_composer(self, input_locator, max_depth=8):
        locator = self.composer_locator if self.composer_locator._count == 1 else None
        return ReplyComposerSearchResult(locator, "fake_composer", self.composer_locator._count, 3 if locator else None)

    async def find_send_action(self, input_locator=None, composer=None):
        if composer is not None:
            locator = self.composer_send_locator if self.composer_send_locator._count == 1 else None
            return LocatorSearchResult(locator, "fake_composer_send", self.composer_send_locator._count)
        locator = self.global_send_locator if self.global_send_locator._count == 1 else None
        return LocatorSearchResult(locator, "fake_global_send", self.global_send_locator._count)

    async def verify_reply_sent(self, request, input_locator, timeout_seconds=15):
        if self.verify_exc:
            raise self.verify_exc
        return self.verification or {"verified": True, "strategy": "fake", "evidence": {"visible": True}}

    async def page_has_existing_reply(self, comment_node, reply_text):
        return self.existing_reply

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


def test_real_send_locate_block_writes_history(tmp_path):
    payload = run(FakePage(locate_count=0), request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["status"] == "blocked"
    assert payload["result"]["blocking_reasons"] == ["comment_not_found"]
    history = (tmp_path / "history.jsonl").read_text(encoding="utf-8")
    assert '"status": "blocked"' in history
    assert '"error_type": "comment_not_found"' in history


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

    assert payload["result"]["dry_run"] is False
    assert payload["result"]["status"] == "cancelled"
    assert payload["result"]["cancelled"] is True
    assert payload["result"]["sent"] is False
    assert "真实发送需要 --yes" in payload["diagnostics"]["send_gate"]
    history = (tmp_path / "history.jsonl").read_text(encoding="utf-8")
    assert '"status": "cancelled"' in history


def test_confirm_send_with_yes_sends_and_writes_history(tmp_path):
    page = FakePage()

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["sent"] is True
    assert payload["result"]["status"] == "verified"
    assert payload["result"]["send_action_performed"] is True
    assert payload["diagnostics"]["send_action_count"] == 1
    assert page.send_locator.click_count == 1
    assert payload["result"]["verified"] is True
    assert page.send_locator.clicked is True
    history = (tmp_path / "history.jsonl").read_text(encoding="utf-8")
    assert '"comment_id": "c1"' in history
    assert '"idempotency_key":' in history


def test_reply_allowed_false_blocks_before_send_path(tmp_path):
    page = FakePage()

    payload = run(
        page,
        request(confirm_send=True, yes=True, reply_allowed=False, target_policy="discovery_only", ownership_status="third_party"),
        tmp_path,
    )

    assert payload["result"]["status"] == "blocked"
    assert payload["result"]["blocking_reasons"] == ["source_not_allowed"]
    assert payload["diagnostics"]["send_action_count"] == 0
    assert page.composer_send_locator.click_count == 0


def test_scoped_send_ignores_global_send_like_buttons(tmp_path):
    page = FakePage(send_count=7, composer_send_count=1)

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["status"] == "verified"
    assert payload["diagnostics"]["reply_composer_found"] is True
    assert payload["diagnostics"]["reply_composer_strategy"] == "fake_composer"
    assert payload["diagnostics"]["reply_composer_depth"] == 3
    assert payload["diagnostics"]["composer_send_action_matched_count"] == 1
    assert payload["diagnostics"]["send_action"]["strategy"] == "fake_composer_send"
    assert page.global_send_locator.click_count == 0
    assert page.composer_send_locator.click_count == 1


def test_composer_send_action_must_be_unique(tmp_path):
    page = FakePage(send_count=7, composer_send_count=2)

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["stage"] == "find_send_action"
    assert payload["result"]["status"] == "blocked"
    assert payload["result"]["blocking_reasons"] == ["send_action_not_unique"]
    assert payload["diagnostics"]["composer_send_action_matched_count"] == 2
    assert page.composer_send_locator.click_count == 0


def test_missing_reply_composer_blocks_before_send(tmp_path):
    page = FakePage(composer_count=0)

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["stage"] == "find_reply_composer"
    assert payload["result"]["status"] == "blocked"
    assert payload["result"]["error_type"] == "reply_composer_not_found"
    assert page.composer_send_locator.click_count == 0


def test_find_reply_composer_and_scoped_send_are_testable():
    page = FakePage(send_count=7, composer_send_count=1)

    composer = asyncio.run(find_reply_composer(page, page.input_locator))
    send_action = asyncio.run(find_send_action(page, page.input_locator, composer=composer.locator))

    assert composer.matched_count == 1
    assert send_action.matched_count == 1
    assert send_action.locator is page.composer_send_locator


def test_acceptance_preview_locates_composer_without_filling_or_clearing(tmp_path):
    page = FakePage(send_count=7, composer_send_count=1)
    page.input_locator.text = "Hello"

    payload = run(page, request(acceptance_test=True, preview_only=True), tmp_path)

    assert payload["result"]["stage"] == "preview_only"
    assert payload["result"]["status"] == "ready"
    assert payload["diagnostics"]["reply_composer_found"] is True
    assert payload["diagnostics"]["composer_send_action_matched_count"] == 1
    assert payload["diagnostics"]["existing_draft_text"] == "Hello"
    assert payload["diagnostics"]["reuse_existing_draft"] is True
    assert page.input_locator.filled_values == []
    assert page.composer_send_locator.click_count == 0


def test_reply_click_without_obstruction_uses_single_normal_click(tmp_path):
    page = FakePage()

    payload = run(page, request(), tmp_path)

    diagnostics = payload["diagnostics"]
    assert page.comment_node.reply_locator.click_count == 1
    assert diagnostics["reply_click_attempts"] == 1
    assert diagnostics["obstruction_detected"] is False
    assert diagnostics["reply_click_obstructed"] is False


def test_reply_click_pointer_intercept_dismisses_relocates_and_recovers(tmp_path):
    page = FakePage(
        reply_click_excs=[RuntimeError("locator.click: subtree intercepts pointer events"), None],
        input_counts=[0, 1],
        obstruction={"obstruction_found": True, "obstruction_types": ["top_overlay"], "dismissable_count": 1, "diagnostics": []},
        dismiss_result={"dismissed_count": 1, "attempts": [{"strategy": "safe_button_label", "matched_count": 1}]},
    )

    payload = run(page, request(), tmp_path)
    diagnostics = payload["diagnostics"]

    assert payload["result"]["stage"] == "dry_run_complete"
    assert page.locate_calls == 2
    assert page.dismiss_calls == 1
    assert page.comment_node.reply_locator.click_count == 1
    assert diagnostics["obstruction_detected"] is True
    assert diagnostics["obstruction_types"] == ["top_overlay"]
    assert diagnostics["obstruction_dismiss_attempted"] is True
    assert diagnostics["obstruction_dismissed_count"] == 1
    assert diagnostics["reply_click_attempts"] == 2
    assert diagnostics["reply_click_obstructed"] is True
    assert diagnostics["reply_click_recovered"] is True


def test_reply_retry_reuses_existing_input_without_second_click(tmp_path):
    page = FakePage(
        reply_click_excs=[RuntimeError("locator.click: subtree intercepts pointer events")],
        input_counts=[1],
        obstruction={"obstruction_found": True, "obstruction_types": ["notification_drawer"], "dismissable_count": 1, "diagnostics": []},
        dismiss_result={"dismissed_count": 1, "attempts": []},
    )

    payload = run(page, request(), tmp_path)
    diagnostics = payload["diagnostics"]

    assert payload["result"]["stage"] == "dry_run_complete"
    assert page.comment_node.reply_locator.click_count == 0
    assert diagnostics["reply_click_attempts"] == 2
    assert diagnostics["reply_input_already_present_before_retry"] is True
    assert diagnostics["reply_click_recovered"] is True


def test_reply_click_recovery_stops_after_two_obstructed_attempts(tmp_path):
    page = FakePage(
        reply_click_excs=[
            RuntimeError("locator.click: intercepts pointer events"),
            RuntimeError("locator.click: intercepts pointer events"),
        ],
        input_counts=[0, 0],
        obstruction={"obstruction_found": True, "obstruction_types": ["top_overlay"], "dismissable_count": 1, "diagnostics": []},
        dismiss_result={"dismissed_count": 0, "attempts": []},
    )

    payload = run(page, request(), tmp_path)

    assert payload["result"]["stage"] == "click_reply_action"
    assert payload["result"]["status"] == "blocked"
    assert payload["result"]["error_type"] == "reply_action_obstructed"
    assert payload["diagnostics"]["reply_click_attempts"] == 2
    assert payload["diagnostics"]["reply_click_recovered"] is False


def test_find_send_action_source_does_not_use_global_first_or_nth():
    source = inspect.getsource(find_send_action)

    assert ".first" not in source
    assert ".nth(" not in source


def test_reply_obstruction_recovery_does_not_use_force_or_dom_click():
    source = inspect.getsource(click_reply_action_with_recovery)

    assert "force=True" not in source
    assert "dispatchEvent" not in source
    assert ".click()" not in source


def test_existing_matching_draft_is_reused_for_real_send(tmp_path):
    page = FakePage()
    page.input_locator.text = "Hello"

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["status"] == "verified"
    assert payload["diagnostics"]["existing_draft_text"] == "Hello"
    assert payload["diagnostics"]["reuse_existing_draft"] is True
    assert page.input_locator.filled_values == []
    assert page.composer_send_locator.click_count == 1


def test_unexpected_existing_draft_blocks_without_overwrite(tmp_path):
    page = FakePage()
    page.input_locator.text = "Different draft"

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["stage"] == "existing_draft_check"
    assert payload["result"]["status"] == "blocked"
    assert payload["result"]["error_type"] == "unexpected_existing_draft"
    assert page.input_locator.filled_values == []
    assert page.composer_send_locator.click_count == 0


def test_author_mention_draft_is_ignored_and_overwritten(tmp_path):
    page = FakePage()
    page.input_locator.text = "Alice "

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["status"] == "verified"
    assert payload["diagnostics"]["existing_draft_text"] == "Alice "
    assert payload["diagnostics"]["ignored_existing_draft"] is True
    assert page.input_locator.filled_values == ["Hello"]
    assert page.composer_send_locator.click_count == 1


def test_final_send_precheck_blocks_if_text_changes_after_scoped_lookup(tmp_path):
    page = FakePage()
    original_find_send = page.find_send_action

    async def mutate_after_lookup(input_locator=None, composer=None):
        result = await original_find_send(input_locator=input_locator, composer=composer)
        if composer is not None:
            page.input_locator.text = "Changed"
        return result

    page.find_send_action = mutate_after_lookup

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["stage"] == "final_send_precheck"
    assert payload["result"]["status"] == "blocked"
    assert payload["result"]["error_type"] == "final_send_precheck_failed"
    assert payload["diagnostics"]["final_send_precheck"]["reason"] == "reply_text_mismatch_before_send"
    assert page.composer_send_locator.click_count == 0


def test_send_action_count_remains_single_send(tmp_path):
    page = FakePage()

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["diagnostics"]["send_action_count"] == 1
    assert page.composer_send_locator.click_count == 1


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

    assert checkpoint["result"]["stage"] == "preflight"
    assert captcha["result"]["stage"] == "preflight"
    assert checkpoint["result"]["status"] == "blocked"
    assert captcha["result"]["status"] == "blocked"


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
    assert refused["result"]["status"] == "duplicate"
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


def test_local_history_duplicate_uses_idempotency_key(tmp_path):
    history_path = tmp_path / "history.jsonl"
    req = request()
    key = build_reply_idempotency_key(req)
    history_path.write_text(
        json.dumps({"status": "verified", "verified": True, "idempotency_key": key, "reply_text": req.reply_text}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    payload = asyncio.run(
        reply_to_comment(FakePage(), request(confirm_send=True, yes=True), artifacts_dir=tmp_path / "replies", history_path=history_path)
    )

    assert payload["result"]["status"] == "duplicate"
    assert payload["result"]["sent"] is False
    assert payload["result"]["already_replied"] is True


def test_page_existing_reply_blocks_as_duplicate(tmp_path):
    payload = run(FakePage(existing_reply=True), request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["status"] == "duplicate"
    assert payload["result"]["already_replied"] is True
    assert payload["result"]["sent"] is False


def test_unverified_send_records_failed_sent_state(tmp_path):
    page = FakePage(verification={"verified": False, "strategy": "timeout", "evidence": {}})

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["status"] == "unverified"
    assert payload["result"]["send_action_performed"] is True
    assert payload["result"]["verified"] is False
    assert payload["result"]["sent"] is False
    assert page.send_locator.click_count == 1
    history = (tmp_path / "history.jsonl").read_text(encoding="utf-8")
    assert '"status": "unverified"' in history


def test_send_action_exception_records_send_failed(tmp_path):
    page = FakePage(send_click_exc=RuntimeError("click failed"))

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["status"] == "send_failed"
    assert payload["result"]["sent"] is False
    assert payload["result"]["error_type"] == "RuntimeError"


def test_unverified_previous_attempt_blocks_before_send(tmp_path):
    history_path = tmp_path / "history.jsonl"
    req = request()
    history_path.write_text(
        json.dumps(
            {
                "status": "unverified",
                "idempotency_key": build_reply_idempotency_key(req),
                "comment_id": req.comment_id,
                "reply_text": req.reply_text,
                "send_action_performed": True,
                "verified": False,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    page = FakePage()

    payload = asyncio.run(
        reply_to_comment(page, request(confirm_send=True, yes=True), artifacts_dir=tmp_path / "replies", history_path=history_path)
    )

    assert payload["result"]["status"] == "blocked_unverified_previous_attempt"
    assert payload["result"]["error_type"] == "unverified_previous_attempt"
    assert payload["result"]["sent"] is False
    assert page.send_locator.click_count == 0


def test_verification_exception_after_send_is_unverified_and_audited(tmp_path):
    page = FakePage(verify_exc=RuntimeError("verification crashed"))

    payload = run(page, request(confirm_send=True, yes=True), tmp_path)

    assert payload["result"]["status"] == "unverified"
    assert payload["result"]["send_action_performed"] is True
    assert payload["result"]["verified"] is False
    assert payload["result"]["sent"] is False
    assert payload["result"]["error_type"] == "RuntimeError"
    assert page.send_locator.click_count == 1
    history_lines = (tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()
    assert any('"status": "unverified"' in line for line in history_lines)
    assert any("verification crashed" in line for line in history_lines)


def test_acceptance_summary_fields_are_recorded(tmp_path):
    payload = run(FakePage(), request(confirm_send=True, yes=True, acceptance_test=True), tmp_path)

    preconditions = payload["diagnostics"]["acceptance_preconditions"]
    assert [item["name"] for item in preconditions] == [
        "Single lead selected",
        "Comment uniquely located",
        "Reply text present",
        "No verified local duplicate",
        "No page duplicate",
        "Preflight passed",
        "Explicit send confirmation present",
    ]
    assert all(item["pass"] for item in preconditions)


def test_reply_history_audits_without_secrets(tmp_path):
    payload = run(FakePage(), request(confirm_send=True, yes=True), tmp_path)
    history = (tmp_path / "history.jsonl").read_text(encoding="utf-8")
    item = json.loads(history.splitlines()[-1])

    assert item["status"] == "verified"
    assert item["reply_source"] == "manual"
    assert item["send_action_performed"] is True
    assert item["sent"] is True
    assert "Cookie" not in history
    assert "Authorization" not in history
    assert "API Key" not in history
    assert payload["result"]["idempotency_key"] == item["idempotency_key"]


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
