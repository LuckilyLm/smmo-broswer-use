import argparse
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
