from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import CommentItem, LeadAnalysisResult, PostItem, WorkflowConfig, WorkflowState


class SQLiteLeadStorage:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS lead_tasks (
                    task_id TEXT PRIMARY KEY,
                    keyword TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    dry_run INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'IDLE',
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    posts_found INTEGER NOT NULL DEFAULT 0,
                    posts_scanned INTEGER NOT NULL DEFAULT 0,
                    comments_scanned INTEGER NOT NULL DEFAULT 0,
                    leads_found INTEGER NOT NULL DEFAULT 0,
                    replies_sent INTEGER NOT NULL DEFAULT 0,
                    failures INTEGER NOT NULL DEFAULT 0,
                    errors_json TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS posts (
                    task_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    scan_status TEXT NOT NULL DEFAULT 'pending',
                    error TEXT,
                    PRIMARY KEY (task_id, url)
                );
                CREATE TABLE IF NOT EXISTS comments (
                    task_id TEXT NOT NULL,
                    comment_id TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    post_url TEXT NOT NULL,
                    author TEXT NOT NULL,
                    text TEXT NOT NULL,
                    reply_target_hint TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL,
                    PRIMARY KEY (task_id, comment_id),
                    UNIQUE (task_id, post_url, dedupe_key)
                );
                CREATE TABLE IF NOT EXISTS leads (
                    task_id TEXT NOT NULL,
                    comment_id TEXT NOT NULL,
                    is_lead INTEGER NOT NULL,
                    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
                    reason TEXT NOT NULL,
                    category TEXT NOT NULL CHECK (category IN (
                        'price', 'purchase', 'link', 'tutorial', 'service',
                        'problem', 'cooperation', 'interest', 'other'
                    )),
                    PRIMARY KEY (task_id, comment_id)
                );
                CREATE TABLE IF NOT EXISTS reply_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    comment_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    reply_text TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('claimed', 'success', 'failed')),
                    verified INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    claimed_at TEXT NOT NULL,
                    finished_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_or_successful_reply
                ON reply_records(comment_id, account_id)
                WHERE status IN ('claimed', 'success');
                """
            )

    def create_task(self, task_id: str, config: WorkflowConfig) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO lead_tasks "
                "(task_id, keyword, config_json, dry_run, status, created_at, started_at) "
                "VALUES (?, ?, ?, ?, 'IDLE', ?, ?)",
                (task_id, config.keyword, config.model_dump_json(), int(config.dry_run), now, now),
            )

    def update_task_state(self, state: WorkflowState) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE lead_tasks SET status = ?, started_at = ?, finished_at = ?, "
                "posts_found = ?, posts_scanned = ?, comments_scanned = ?, leads_found = ?, "
                "replies_sent = ?, failures = ?, errors_json = ? WHERE task_id = ?",
                (
                    state.status.value,
                    state.started_at.isoformat(),
                    state.finished_at.isoformat() if state.finished_at else None,
                    state.posts_found,
                    state.posts_scanned,
                    state.comments_scanned,
                    state.leads_found,
                    state.replies_sent,
                    state.failures,
                    json.dumps(state.errors, ensure_ascii=False),
                    state.task_id,
                ),
            )

    def update_task_status(self, task_id: str, status: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE lead_tasks SET status = ? WHERE task_id = ?", (status, task_id))

    def get_task(self, task_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM lead_tasks WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def save_post(self, task_id: str, post: PostItem) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO posts "
                "(task_id, url, title, platform, discovered_at, scan_status, error) "
                "VALUES (?, ?, ?, ?, ?, 'pending', NULL)",
                (task_id, post.url, post.title, post.platform, post.discovered_at.isoformat()),
            )

    def update_post_scan(self, task_id: str, post_url: str, status: str, error: str | None = None) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE posts SET scan_status = ?, error = ? WHERE task_id = ? AND url = ?",
                (status, error, task_id, post_url),
            )

    def get_post(self, task_id: str, post_url: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM posts WHERE task_id = ? AND url = ?", (task_id, post_url)
            ).fetchone()
        return dict(row) if row else None

    def save_comment(self, task_id: str, comment: CommentItem) -> None:
        dedupe_key = comment.external_id or comment.comment_id
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO comments "
                "(task_id, comment_id, external_id, post_url, author, text, reply_target_hint, dedupe_key) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task_id, comment.comment_id, comment.external_id, comment.post_url,
                    comment.author, comment.text, comment.reply_target_hint, dedupe_key,
                ),
            )

    def save_lead(self, task_id: str, analysis: LeadAnalysisResult) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO leads "
                "(task_id, comment_id, is_lead, score, reason, category) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    task_id, analysis.comment_id, int(analysis.is_lead), analysis.score,
                    analysis.reason, analysis.category,
                ),
            )

    def claim_reply(self, task_id: str, comment_id: str, account_id: str, reply_text: str) -> bool:
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO reply_records "
                    "(task_id, comment_id, account_id, reply_text, status, claimed_at) "
                    "VALUES (?, ?, ?, ?, 'claimed', ?)",
                    (task_id, comment_id, account_id, reply_text, datetime.now(timezone.utc).isoformat()),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    def finalize_reply(
        self, task_id: str, comment_id: str, account_id: str, success: bool,
        error: str | None = None, verified: bool = False,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE reply_records SET status = ?, verified = ?, error = ?, finished_at = ? "
                "WHERE task_id = ? AND comment_id = ? AND account_id = ? AND status = 'claimed'",
                (
                    "success" if success else "failed", int(verified), error,
                    datetime.now(timezone.utc).isoformat(), task_id, comment_id, account_id,
                ),
            )

    def record_reply(self, task_id: str, comment_id: str, reply_text: str, success: bool) -> bool:
        if not self.claim_reply(task_id, comment_id, "default", reply_text):
            return False
        self.finalize_reply(task_id, comment_id, "default", success, None if success else "Reply failed")
        return True

    def has_successful_reply(self, comment_id: str, account_id: str = "default") -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM reply_records WHERE comment_id = ? AND account_id = ? "
                "AND status = 'success' LIMIT 1",
                (comment_id, account_id),
            ).fetchone()
        return row is not None

    def result_rows(self, task_id: str, lead_threshold: int, dry_run: bool) -> list[list]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.post_url, c.author, c.text, l.score, l.reason, l.category,
                       r.status AS reply_status, r.error
                FROM comments c
                JOIN leads l ON l.task_id = c.task_id AND l.comment_id = c.comment_id
                LEFT JOIN reply_records r ON r.id = (
                    SELECT rr.id FROM reply_records rr
                    WHERE rr.task_id = c.task_id AND rr.comment_id = c.comment_id
                    ORDER BY rr.id DESC LIMIT 1
                )
                WHERE c.task_id = ? AND l.is_lead = 1 AND l.score >= ?
                ORDER BY c.rowid
                """,
                (task_id, lead_threshold),
            ).fetchall()
        return [
            [
                row["post_url"], row["author"], row["text"], row["score"], row["reason"],
                row["category"], "dry_run" if dry_run else (row["reply_status"] or "not_sent"),
                row["error"] or "",
            ]
            for row in rows
        ]

    def count_rows(self, table: str) -> int:
        allowed_tables = {"lead_tasks", "posts", "comments", "leads", "reply_records"}
        if table not in allowed_tables:
            raise ValueError(f"Unsupported table: {table}")
        with self._connect() as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
