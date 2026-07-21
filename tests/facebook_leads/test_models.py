from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.facebook_leads.models import (
    CommentItem,
    LeadAnalysisResult,
    PostItem,
    ReplyRecord,
    WorkflowConfig,
    WorkflowState,
    WorkflowStatus,
)


def test_workflow_config_matches_business_defaults():
    config = WorkflowConfig()

    assert config.keyword == "AI video"
    assert config.max_posts == 10
    assert config.max_comments_per_post == 20
    assert config.lead_threshold == 75
    assert config.max_replies == 1
    assert config.reply_text == "你好"
    assert config.dry_run is True
    assert config.account_id == "default"
    assert config.target_customer_description
    assert not hasattr(config, "reply_enabled")
    assert not hasattr(config, "min_lead_score")
    assert not hasattr(config, "search_queries")


@pytest.mark.parametrize("score", [-1, 101])
def test_analysis_rejects_scores_outside_zero_to_one_hundred(score):
    with pytest.raises(ValidationError):
        LeadAnalysisResult(
            comment_id="comment-1",
            is_lead=True,
            score=score,
            reason="intent",
            category="interest",
        )


def test_analysis_rejects_unknown_category():
    with pytest.raises(ValidationError):
        LeadAnalysisResult(
            comment_id="comment-1",
            is_lead=True,
            score=80,
            reason="intent",
            category="unknown",
        )


def test_item_models_expose_required_business_fields():
    discovered_at = datetime.now(timezone.utc)
    post = PostItem(
        url="https://example.test/post-1",
        title="AI video discussion",
        platform="facebook",
        discovered_at=discovered_at,
    )
    comment = CommentItem(
        comment_id="comment-1",
        external_id="external-1",
        post_url=post.url,
        author="Alice",
        text="How much does this cost?",
        reply_target_hint="Reply button near Alice's comment",
    )
    analysis = LeadAnalysisResult(
        comment_id=comment.comment_id,
        is_lead=True,
        score=80,
        reason="Asked about price",
        category="price",
    )

    assert post.discovered_at == discovered_at
    assert comment.post_url == post.url
    assert analysis.category == "price"


def test_workflow_state_tracks_required_fields_and_guarded_transitions():
    state = WorkflowState(task_id="task-1", keyword="AI video")

    state.transition_to(WorkflowStatus.SEARCHING)
    state.transition_to(WorkflowStatus.COLLECTING_POSTS)

    assert state.status_history == [
        WorkflowStatus.IDLE,
        WorkflowStatus.SEARCHING,
        WorkflowStatus.COLLECTING_POSTS,
    ]
    assert state.posts_found == 0
    assert state.posts_scanned == 0
    assert state.comments_scanned == 0
    assert state.leads_found == 0
    assert state.replies_sent == 0
    assert state.failures == 0
    assert state.errors == []
    assert state.started_at is not None
    assert state.finished_at is None

    with pytest.raises(ValueError, match="Invalid workflow transition"):
        state.transition_to(WorkflowStatus.DONE)


def test_terminal_transition_sets_finished_at():
    state = WorkflowState(task_id="task-1", keyword="AI video")
    state.transition_to(WorkflowStatus.STOPPED)

    assert state.finished_at is not None


def test_reply_record_exposes_phase_two_lifecycle_fields():
    now = datetime.now(timezone.utc)
    record = ReplyRecord(
        task_id="task-1",
        comment_id="comment-1",
        account_id="default",
        reply_text="你好",
        status="success",
        verified=False,
        error=None,
        claimed_at=now,
        finished_at=now,
    )

    assert record.status == "success"
    assert record.account_id == "default"
    assert record.finished_at == now
