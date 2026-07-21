import argparse
import asyncio
from pathlib import Path

import scripts.facebook_lead_scan as lead_scan


def test_lead_scan_search_mode_generates_report(monkeypatch, tmp_path):
    async def fake_scan(args):
        artifact_dir = tmp_path / "run"
        artifact_dir.mkdir()
        return {
            "success": True,
            "stage": "completed",
            "keyword": args.keyword,
            "contents": [
                {
                    "url": "https://www.facebook.com/reel/1",
                    "content_type": "reel",
                    "text_preview": "Demo",
                    "author_name": None,
                }
            ],
            "comments": [
                {
                    "comment_id": None,
                    "author_name": "Alice",
                    "author_url": None,
                    "text": "How much?",
                    "timestamp_text": None,
                    "comment_url": None,
                    "is_reply": False,
                    "parent_comment_id": None,
                    "source_content_url": "https://www.facebook.com/reel/1",
                    "fingerprint": "fp1",
                }
            ],
            "timing": {},
            "diagnostics": {"artifact_dir": str(artifact_dir), "result_path": str(artifact_dir / "result.json")},
        }

    monkeypatch.setattr(lead_scan, "run_cli_scan", fake_scan)
    payload = asyncio.run(
        lead_scan.run_lead_scan(
            argparse.Namespace(
                keyword="car detailing",
                content_limit=1,
                comment_limit=10,
                max_scrolls=1,
                max_expand_clicks=1,
                current_page_only=False,
                output_dir=str(tmp_path),
                output=None,
                llm_review=False,
                llm_batch_size=10,
                llm_model=None,
                llm_client=None,
            )
        )
    )

    assert payload["lead_report"]["lead_candidate_count"] == 1
    assert Path(payload["paths"]["lead_report_html"]).exists()


def test_lead_scan_current_page_only_generates_report(monkeypatch, tmp_path):
    async def fake_scan(args):
        artifact_dir = tmp_path / "run"
        artifact_dir.mkdir()
        assert args.current_page_only is True
        return {
            "success": True,
            "stage": "completed",
            "keyword": None,
            "contents": [{"url": "https://www.facebook.com/reel/1", "content_type": "unknown"}],
            "comments": [],
            "timing": {},
            "diagnostics": {"artifact_dir": str(artifact_dir), "result_path": str(artifact_dir / "result.json")},
        }

    monkeypatch.setattr(lead_scan, "run_cli_scan", fake_scan)
    payload = asyncio.run(
        lead_scan.run_lead_scan(
            argparse.Namespace(
                keyword=None,
                content_limit=1,
                comment_limit=10,
                max_scrolls=1,
                max_expand_clicks=1,
                current_page_only=True,
                output_dir=str(tmp_path),
                output=None,
                llm_review=False,
                llm_batch_size=10,
                llm_model=None,
                llm_client=None,
            )
        )
    )

    assert payload["lead_report"]["scanned_content_count"] == 1


def test_lead_scan_source_has_no_agent_llm_or_facebook_write_actions():
    project_root = Path(__file__).parents[2]
    source = (project_root / "scripts/facebook_lead_scan.py").read_text(encoding="utf-8")
    report_source = (project_root / "src/facebook_leads/facebook/report.py").read_text(encoding="utf-8")
    intent_source = (project_root / "src/facebook_leads/facebook/intent.py").read_text(encoding="utf-8")
    combined = "\n".join([source, report_source, intent_source])

    forbidden = [
        "BrowserUseAgent",
        "get_llm_model",
        ".fill(",
        "keyboard.type",
        "reply(",
        "like(",
        "follow(",
        "message(",
        "post(",
    ]
    for snippet in forbidden:
        assert snippet not in combined
