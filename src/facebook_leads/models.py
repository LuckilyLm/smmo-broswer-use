from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    IDLE = "IDLE"
    SEARCHING = "SEARCHING"
    COLLECTING_POSTS = "COLLECTING_POSTS"
    SCANNING_POST = "SCANNING_POST"
    EXTRACTING_COMMENTS = "EXTRACTING_COMMENTS"
    ANALYZING = "ANALYZING"
    REPLYING = "REPLYING"
    VERIFYING = "VERIFYING"
    DONE = "DONE"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class WorkflowConfig(BaseModel):
    keyword: str = "AI video"
    max_posts: int = Field(default=10, gt=0)
    max_comments_per_post: int = Field(default=20, gt=0)
    lead_threshold: int = Field(default=75, ge=0, le=100)
    max_replies: int = Field(default=1, ge=0)
    reply_text: str = "你好"
    target_customer_description: str = (
        "寻找对 AI 视频生成感兴趣，并有购买相关产品或服务意向的潜在客户"
    )
    account_id: str = "default"
    dry_run: bool = True


class PostItem(BaseModel):
    url: str
    title: str
    platform: str
    discovered_at: datetime


class CommentItem(BaseModel):
    comment_id: str
    external_id: str
    post_url: str
    author: str
    text: str
    reply_target_hint: str


LeadCategory = Literal[
    "price",
    "purchase",
    "link",
    "tutorial",
    "service",
    "problem",
    "cooperation",
    "interest",
    "other",
]


class LeadAnalysisResult(BaseModel):
    comment_id: str
    is_lead: bool
    score: int = Field(ge=0, le=100)
    reason: str
    category: LeadCategory


class ReplyRecord(BaseModel):
    task_id: str
    comment_id: str
    account_id: str
    reply_text: str
    status: Literal["claimed", "success", "failed"]
    verified: bool = False
    error: str | None = None
    claimed_at: datetime
    finished_at: datetime | None = None


_ALLOWED_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    WorkflowStatus.IDLE: {WorkflowStatus.SEARCHING},
    WorkflowStatus.SEARCHING: {WorkflowStatus.COLLECTING_POSTS},
    WorkflowStatus.COLLECTING_POSTS: {
        WorkflowStatus.SCANNING_POST,
        WorkflowStatus.VERIFYING,
    },
    WorkflowStatus.SCANNING_POST: {WorkflowStatus.EXTRACTING_COMMENTS},
    WorkflowStatus.EXTRACTING_COMMENTS: {
        WorkflowStatus.ANALYZING,
        WorkflowStatus.SCANNING_POST,
        WorkflowStatus.VERIFYING,
    },
    WorkflowStatus.ANALYZING: {
        WorkflowStatus.REPLYING,
        WorkflowStatus.SCANNING_POST,
        WorkflowStatus.VERIFYING,
    },
    WorkflowStatus.REPLYING: {
        WorkflowStatus.REPLYING,
        WorkflowStatus.SCANNING_POST,
        WorkflowStatus.VERIFYING,
    },
    WorkflowStatus.VERIFYING: {WorkflowStatus.DONE},
    WorkflowStatus.DONE: set(),
    WorkflowStatus.STOPPED: set(),
    WorkflowStatus.FAILED: set(),
}
_TERMINAL_STATUSES = {
    WorkflowStatus.DONE,
    WorkflowStatus.STOPPED,
    WorkflowStatus.FAILED,
}


class WorkflowState(BaseModel):
    task_id: str
    status: WorkflowStatus = WorkflowStatus.IDLE
    keyword: str
    current_post: str | None = None
    posts_found: int = 0
    posts_scanned: int = 0
    comments_scanned: int = 0
    leads_found: int = 0
    replies_sent: int = 0
    failures: int = 0
    errors: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    status_history: list[WorkflowStatus] = Field(
        default_factory=lambda: [WorkflowStatus.IDLE]
    )

    def transition_to(self, status: WorkflowStatus) -> None:
        allowed = _ALLOWED_TRANSITIONS[self.status]
        if status not in allowed and not (
            status in {WorkflowStatus.STOPPED, WorkflowStatus.FAILED}
            and self.status not in _TERMINAL_STATUSES
        ):
            raise ValueError(
                f"Invalid workflow transition: {self.status.value} -> {status.value}"
            )
        self.status = status
        self.status_history.append(status)
        if status in _TERMINAL_STATUSES:
            self.finished_at = datetime.now(timezone.utc)
