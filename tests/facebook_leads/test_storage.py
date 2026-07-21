from concurrent.futures import ThreadPoolExecutor
import sqlite3
from datetime import datetime, timezone

from src.facebook_leads.models import CommentItem, LeadAnalysisResult, PostItem, WorkflowConfig
from src.facebook_leads.storage import SQLiteLeadStorage


def test_storage_creates_required_tables_and_columns(tmp_path):
    storage = SQLiteLeadStorage(tmp_path / "leads.db")

    with sqlite3.connect(storage.path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        task_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(lead_tasks)")
        }
        post_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(posts)")
        }
        comment_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(comments)")
        }
        lead_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(leads)")
        }
        reply_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(reply_records)")
        }

    assert {"lead_tasks", "posts", "comments", "leads", "reply_records"} <= tables
    assert {
        "created_at",
        "started_at",
        "finished_at",
        "posts_found",
        "posts_scanned",
        "comments_scanned",
        "leads_found",
        "replies_sent",
        "failures",
        "errors_json",
    } <= task_columns
    assert {"url", "title", "platform", "discovered_at", "scan_status", "error"} <= post_columns
    assert {
        "comment_id",
        "external_id",
        "post_url",
        "author",
        "text",
        "reply_target_hint",
        "dedupe_key",
    } <= comment_columns
    assert {"comment_id", "is_lead", "score", "reason", "category"} <= lead_columns
    assert {
        "task_id",
        "comment_id",
        "account_id",
        "reply_text",
        "status",
        "verified",
        "error",
        "claimed_at",
        "finished_at",
    } <= reply_columns


def test_storage_creates_missing_parent_directory(tmp_path):
    database_path = tmp_path / "nested" / "data" / "leads.db"

    storage = SQLiteLeadStorage(database_path)

    assert storage.path == database_path
    assert database_path.exists()


def test_storage_persists_aligned_models(tmp_path):
    storage = SQLiteLeadStorage(tmp_path / "leads.db")
    config = WorkflowConfig()
    post = PostItem(
        url="https://example.test/post-1",
        title="AI video",
        platform="facebook",
        discovered_at=datetime.now(timezone.utc),
    )
    comment = CommentItem(
        comment_id="comment-1",
        external_id="external-1",
        post_url=post.url,
        author="Alice",
        text="What is the price?",
        reply_target_hint="reply near comment-1",
    )
    analysis = LeadAnalysisResult(
        comment_id=comment.comment_id,
        is_lead=True,
        score=90,
        reason="Explicit price question",
        category="price",
    )

    storage.create_task("task-1", config)
    storage.save_post("task-1", post)
    storage.save_comment("task-1", comment)
    storage.save_lead("task-1", analysis)

    task = storage.get_task("task-1")
    assert task["keyword"] == "AI video"
    assert task["dry_run"] == 1
    assert storage.count_rows("posts") == 1
    assert storage.count_rows("comments") == 1
    assert storage.count_rows("leads") == 1


def test_only_successful_reply_is_unique_per_comment(tmp_path):
    storage = SQLiteLeadStorage(tmp_path / "leads.db")

    assert storage.record_reply("task-1", "comment-1", "First", success=True)
    assert not storage.record_reply("task-2", "comment-1", "Duplicate", success=True)
    assert not storage.record_reply("task-3", "comment-1", "Failed retry", success=False)
    assert storage.count_rows("reply_records") == 1




def test_atomic_reply_claim_allows_only_one_concurrent_owner(tmp_path):
    storage = SQLiteLeadStorage(tmp_path / "leads.db")

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(
            pool.map(
                lambda task_id: storage.claim_reply(
                    task_id, "comment-1", "default", "你好"
                ),
                ["task-1", "task-2"],
            )
        )

    assert sorted(claims) == [False, True]
    assert storage.count_rows("reply_records") == 1


def test_failed_reply_claim_can_be_retried(tmp_path):
    storage = SQLiteLeadStorage(tmp_path / "leads.db")

    assert storage.claim_reply("task-1", "comment-1", "default", "你好")
    storage.finalize_reply("task-1", "comment-1", "default", success=False, error="failed")
    assert storage.claim_reply("task-2", "comment-1", "default", "再试")
