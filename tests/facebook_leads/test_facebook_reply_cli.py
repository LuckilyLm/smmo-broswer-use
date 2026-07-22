import argparse
import asyncio
import json

import pytest

import scripts.facebook_reply_one as reply_cli


def test_cli_builds_request_from_one_based_lead_index(tmp_path):
    report = {
        "contents": [
            {
                "leads": [
                    {
                        "comment_fingerprint": "fp1",
                        "comment_id": "c1",
                        "author_name": "Alice",
                        "comment_text": "How much?",
                        "source_content_url": "https://www.facebook.com/reel/1",
                        "direct_comment_url": "https://www.facebook.com/reel/1?comment_id=c1",
                        "intent_score": 3,
                        "intent_level": "medium",
                    }
                ]
            }
        ]
    }
    path = tmp_path / "lead_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    req = reply_cli.build_reply_request(
        argparse.Namespace(
            lead_report=str(path),
            lead_index=1,
            reply_text="Hello",
            use_suggested_reply=False,
            confirm_send=False,
            yes=False,
            keep_filled=False,
            allow_duplicate=False,
            preview_only=False,
            verify_timeout_seconds=15,
            acceptance_test=False,
            source_content_url=None,
            direct_comment_url=None,
            comment_id=None,
            author_name=None,
            comment_text=None,
            fingerprint=None,
        )
    )

    assert req.lead_index == 1
    assert req.comment_id == "c1"
    assert req.reply_text == "Hello"


def test_cli_requires_lead_index_with_report(tmp_path):
    report = tmp_path / "lead_report.json"
    report.write_text('{"contents":[]}', encoding="utf-8")

    with pytest.raises(ValueError, match="lead-index"):
        reply_cli.build_reply_request(
            argparse.Namespace(
                lead_report=str(report),
                lead_index=None,
                reply_text="Hello",
                use_suggested_reply=False,
                confirm_send=False,
                yes=False,
                keep_filled=False,
                allow_duplicate=False,
                source_content_url=None,
                direct_comment_url=None,
                comment_id=None,
                author_name=None,
                comment_text=None,
                fingerprint=None,
            )
        )


def test_cli_supports_direct_parameter_request():
    req = reply_cli.build_reply_request(
        argparse.Namespace(
            lead_report=None,
            lead_index=None,
            reply_text="Hello",
            use_suggested_reply=False,
            confirm_send=True,
            yes=False,
            keep_filled=True,
            allow_duplicate=True,
            preview_only=False,
            verify_timeout_seconds=15,
            acceptance_test=False,
            source_content_url="https://www.facebook.com/reel/1",
            direct_comment_url=None,
            comment_id="c1",
            author_name="Alice",
            comment_text="How much?",
            fingerprint="fp1",
        )
    )

    assert req.source_content_url == "https://www.facebook.com/reel/1"
    assert req.confirm_send is True
    assert req.yes is False
    assert req.keep_filled is True


def test_use_suggested_reply_sets_llm_reply_source(tmp_path):
    report = {
        "contents": [
            {
                "leads": [
                    {
                        "comment_fingerprint": "fp1",
                        "comment_id": "c1",
                        "author_name": "Alice",
                        "comment_text": "How much?",
                        "source_content_url": "https://www.facebook.com/reel/1",
                        "direct_comment_url": "https://www.facebook.com/reel/1?comment_id=c1",
                        "intent_score": 3,
                        "intent_level": "medium",
                        "llm_review": {"suggested_reply": "Hi Alice, please DM us."},
                    }
                ]
            }
        ]
    }
    path = tmp_path / "lead_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    req = reply_cli.build_reply_request(
        argparse.Namespace(
            lead_report=str(path),
            lead_index=1,
            reply_text=None,
            use_suggested_reply=True,
            confirm_send=False,
            yes=False,
            keep_filled=False,
            allow_duplicate=False,
            preview_only=False,
            verify_timeout_seconds=15,
            acceptance_test=False,
            source_content_url=None,
            direct_comment_url=None,
            comment_id=None,
            author_name=None,
            comment_text=None,
            fingerprint=None,
        )
    )

    assert req.reply_text == "Hi Alice, please DM us."
    assert req.reply_source == "llm_suggested"
    assert req.confirm_send is False


def test_yes_without_confirm_send_stays_dry_run_request():
    req = reply_cli.build_reply_request(
        argparse.Namespace(
            lead_report=None,
            lead_index=None,
            reply_text="Hello",
            use_suggested_reply=False,
            confirm_send=False,
            yes=True,
            keep_filled=False,
            allow_duplicate=False,
            preview_only=False,
            verify_timeout_seconds=15,
            acceptance_test=False,
            source_content_url="https://www.facebook.com/reel/1",
            direct_comment_url=None,
            comment_id="c1",
            author_name="Alice",
            comment_text="How much?",
            fingerprint="fp1",
        )
    )

    assert req.confirm_send is False
    assert req.yes is True
    assert req.send_confirmed is False


def test_interactive_confirmation_requires_exact_send(monkeypatch):
    class FakeStdin:
        def __init__(self, value):
            self.value = value

        def isatty(self):
            return True

    monkeypatch.setattr(reply_cli.sys, "stdin", FakeStdin("unused"))
    monkeypatch.setattr("builtins.input", lambda prompt: "SEND")
    assert reply_cli.confirm_interactive(argparse.Namespace()) is True

    monkeypatch.setattr("builtins.input", lambda prompt: "send")
    assert reply_cli.confirm_interactive(argparse.Namespace()) is False


def test_preview_only_does_not_require_browser_cdp(monkeypatch, tmp_path):
    called = {"cdp": False}

    def fail_cdp():
        called["cdp"] = True
        raise AssertionError("BROWSER_CDP should not be read")

    monkeypatch.setattr(reply_cli, "require_browser_cdp", fail_cdp)
    payload = asyncio.run(
        reply_cli.run_reply_one(
            argparse.Namespace(
                lead_report=None,
                lead_index=None,
                reply_text="Hello",
                use_suggested_reply=False,
                confirm_send=False,
                yes=False,
                keep_filled=False,
                allow_duplicate=False,
                preview_only=True,
                verify_timeout_seconds=15,
                acceptance_test=False,
                source_content_url="https://www.facebook.com/reel/1",
                direct_comment_url=None,
                comment_id="c1",
                author_name="Alice",
                comment_text="How much?",
                fingerprint="fp1",
                artifacts_dir=str(tmp_path / "replies"),
                history_path=str(tmp_path / "history.jsonl"),
            )
        )
    )

    assert called["cdp"] is False
    assert payload["result"]["stage"] == "preview_only"
    assert payload["result"]["sent"] is False


def test_unconfirmed_real_send_does_not_require_browser_cdp(monkeypatch, tmp_path):
    called = {"cdp": False}

    class FakeStdin:
        def isatty(self):
            return False

    def fail_cdp():
        called["cdp"] = True
        raise AssertionError("BROWSER_CDP should not be read")

    monkeypatch.setattr(reply_cli.sys, "stdin", FakeStdin())
    monkeypatch.setattr(reply_cli, "require_browser_cdp", fail_cdp)

    payload = asyncio.run(
        reply_cli.run_reply_one(
            argparse.Namespace(
                lead_report=None,
                lead_index=None,
                reply_text="Hello",
                use_suggested_reply=False,
                confirm_send=True,
                yes=False,
                keep_filled=False,
                allow_duplicate=False,
                preview_only=False,
                verify_timeout_seconds=15,
                acceptance_test=False,
                source_content_url="https://www.facebook.com/reel/1",
                direct_comment_url=None,
                comment_id="c1",
                author_name="Alice",
                comment_text="How much?",
                fingerprint="fp1",
                artifacts_dir=str(tmp_path / "replies"),
                history_path=str(tmp_path / "history.jsonl"),
            )
        )
    )

    assert called["cdp"] is False
    assert payload["result"]["status"] == "cancelled"
    assert payload["result"]["sent"] is False


def test_acceptance_test_alone_does_not_send_or_require_cdp(monkeypatch, tmp_path, capsys):
    called = {"cdp": False}

    def fail_cdp():
        called["cdp"] = True
        raise AssertionError("BROWSER_CDP should not be read")

    monkeypatch.setattr(reply_cli, "require_browser_cdp", fail_cdp)

    payload = asyncio.run(
        reply_cli.run_reply_one(
            argparse.Namespace(
                lead_report=None,
                lead_index=None,
                reply_text="Hello",
                use_suggested_reply=False,
                confirm_send=False,
                yes=False,
                keep_filled=False,
                allow_duplicate=False,
                preview_only=False,
                acceptance_test=True,
                verify_timeout_seconds=15,
                source_content_url="https://www.facebook.com/reel/1",
                direct_comment_url=None,
                comment_id="c1",
                author_name="Alice",
                comment_text="How much?",
                fingerprint="fp1",
                artifacts_dir=str(tmp_path / "replies"),
                history_path=str(tmp_path / "history.jsonl"),
            )
        )
    )

    output = capsys.readouterr().out
    assert called["cdp"] is False
    assert payload["result"]["stage"] == "preview_only"
    assert payload["result"]["sent"] is False
    assert "NO REAL SEND WAS ATTEMPTED" in output


def test_acceptance_confirm_send_wrong_input_is_cancelled(monkeypatch, tmp_path):
    class FakeStdin:
        def isatty(self):
            return True

    monkeypatch.setattr(reply_cli.sys, "stdin", FakeStdin())
    monkeypatch.setattr("builtins.input", lambda prompt: "NO")
    monkeypatch.setattr(reply_cli, "require_browser_cdp", lambda: (_ for _ in ()).throw(AssertionError("no cdp")))

    payload = asyncio.run(
        reply_cli.run_reply_one(
            argparse.Namespace(
                lead_report=None,
                lead_index=None,
                reply_text="Hello",
                use_suggested_reply=False,
                confirm_send=True,
                yes=False,
                keep_filled=False,
                allow_duplicate=False,
                preview_only=False,
                acceptance_test=True,
                verify_timeout_seconds=15,
                source_content_url="https://www.facebook.com/reel/1",
                direct_comment_url=None,
                comment_id="c1",
                author_name="Alice",
                comment_text="How much?",
                fingerprint="fp1",
                artifacts_dir=str(tmp_path / "replies"),
                history_path=str(tmp_path / "history.jsonl"),
            )
        )
    )

    assert payload["result"]["status"] == "cancelled"
    assert payload["result"]["sent"] is False


def test_acceptance_confirm_send_exact_send_allows_browser_path(monkeypatch, tmp_path):
    class FakeStdin:
        def isatty(self):
            return True

    called = {"cdp": False}

    monkeypatch.setattr(reply_cli.sys, "stdin", FakeStdin())
    monkeypatch.setattr("builtins.input", lambda prompt: "SEND")

    def stop_at_cdp():
        called["cdp"] = True
        raise reply_cli.BrowserCdpNotConfiguredError("stop before browser")

    monkeypatch.setattr(reply_cli, "require_browser_cdp", stop_at_cdp)

    try:
        asyncio.run(
            reply_cli.run_reply_one(
                argparse.Namespace(
                    lead_report=None,
                    lead_index=None,
                    reply_text="Hello",
                    use_suggested_reply=False,
                    confirm_send=True,
                    yes=False,
                    keep_filled=False,
                    allow_duplicate=False,
                    preview_only=False,
                    acceptance_test=True,
                    verify_timeout_seconds=15,
                    source_content_url="https://www.facebook.com/reel/1",
                    direct_comment_url=None,
                    comment_id="c1",
                    author_name="Alice",
                    comment_text="How much?",
                    fingerprint="fp1",
                    artifacts_dir=str(tmp_path / "replies"),
                    history_path=str(tmp_path / "history.jsonl"),
                )
            )
        )
    except reply_cli.BrowserCdpNotConfiguredError:
        pass

    assert called["cdp"] is True
