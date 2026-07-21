import asyncio
from datetime import datetime, timezone

from src.facebook_leads.adapters import (
    FakeAnalyzerAdapter,
    FakeBrowserAdapter,
    FakeReplyAdapter,
)
from src.facebook_leads.models import CommentItem, LeadAnalysisResult, PostItem, WorkflowConfig, WorkflowStatus
from src.facebook_leads.storage import SQLiteLeadStorage
from src.facebook_leads.workflow import FacebookLeadWorkflow


def _post(number: int = 1) -> PostItem:
    return PostItem(
        url=f"https://example.test/post-{number}",
        title=f"AI video post {number}",
        platform="facebook",
        discovered_at=datetime.now(timezone.utc),
    )


def _comment(number: int, post: PostItem) -> CommentItem:
    return CommentItem(
        comment_id=f"comment-{number}",
        external_id=f"external-{number}",
        post_url=post.url,
        author=f"Author {number}",
        text=f"I want AI video service {number}",
        reply_target_hint=f"reply target {number}",
    )


def _analysis(comment: CommentItem, score: int = 90) -> LeadAnalysisResult:
    return LeadAnalysisResult(
        comment_id=comment.comment_id,
        is_lead=True,
        score=score,
        reason="Purchase intent",
        category="purchase",
    )


def _workflow(tmp_path, posts, comments_by_post, results):
    storage = SQLiteLeadStorage(tmp_path / "leads.db")
    browser = FakeBrowserAdapter(posts=posts, comments_by_post=comments_by_post)
    analyzer = FakeAnalyzerAdapter(results=results)
    replier = FakeReplyAdapter()
    return storage, browser, analyzer, replier, FacebookLeadWorkflow(
        storage, browser, analyzer, replier
    )


def test_analyzes_each_posts_comments_in_one_batch(tmp_path):
    first, second = _post(1), _post(2)
    comments = [_comment(1, first), _comment(2, first), _comment(3, second)]
    results = {comment.comment_id: _analysis(comment) for comment in comments}
    storage, _, analyzer, replier, workflow = _workflow(
        tmp_path,
        [first, second],
        {first.url: comments[:2], second.url: comments[2:]},
        results,
    )

    state = asyncio.run(workflow.run("task-1", WorkflowConfig()))

    assert state.status is WorkflowStatus.DONE
    assert state.posts_found == 2
    assert state.posts_scanned == 2
    assert state.comments_scanned == 3
    assert state.leads_found == 3
    assert analyzer.batch_calls == [["comment-1", "comment-2"], ["comment-3"]]
    assert replier.calls == []
    assert storage.count_rows("leads") == 3


def test_dry_run_never_calls_reply_adapter(tmp_path):
    post = _post()
    comment = _comment(1, post)
    storage, _, _, replier, workflow = _workflow(
        tmp_path, [post], {post.url: [comment]}, {comment.comment_id: _analysis(comment)}
    )

    state = asyncio.run(workflow.run("task-1", WorkflowConfig(dry_run=True)))

    assert state.replies_sent == 0
    assert replier.calls == []
    assert storage.count_rows("reply_records") == 0


def test_non_dry_run_enforces_max_replies(tmp_path):
    post = _post()
    comments = [_comment(1, post), _comment(2, post), _comment(3, post)]
    results = {comment.comment_id: _analysis(comment) for comment in comments}
    storage, _, _, replier, workflow = _workflow(
        tmp_path, [post], {post.url: comments}, results
    )

    state = asyncio.run(
        workflow.run(
            "task-1",
            WorkflowConfig(dry_run=False, max_replies=2, reply_text="你好"),
        )
    )

    assert state.replies_sent == 2
    assert replier.calls == [("comment-1", "你好"), ("comment-2", "你好")]
    assert storage.count_rows("reply_records") == 2


def test_stop_event_checked_after_safe_search_operation(tmp_path):
    stop_event = asyncio.Event()
    post = _post()
    browser = FakeBrowserAdapter(posts=[post], on_search=lambda: stop_event.set())
    storage = SQLiteLeadStorage(tmp_path / "leads.db")
    analyzer = FakeAnalyzerAdapter()
    replier = FakeReplyAdapter()
    workflow = FacebookLeadWorkflow(storage, browser, analyzer, replier)

    state = asyncio.run(
        workflow.run("task-1", WorkflowConfig(), stop_event=stop_event)
    )

    assert state.status is WorkflowStatus.STOPPED
    assert state.posts_found == 1
    assert state.posts_scanned == 0
    assert analyzer.batch_calls == []
    assert replier.calls == []
    assert storage.get_task("task-1")["status"] == "STOPPED"


def test_stop_event_checked_between_comment_batch_and_replies(tmp_path):
    stop_event = asyncio.Event()
    post = _post()
    comment = _comment(1, post)
    analyzer = FakeAnalyzerAdapter(
        results={comment.comment_id: _analysis(comment)},
        on_batch=lambda: stop_event.set(),
    )
    storage = SQLiteLeadStorage(tmp_path / "leads.db")
    browser = FakeBrowserAdapter(posts=[post], comments_by_post={post.url: [comment]})
    replier = FakeReplyAdapter()
    workflow = FacebookLeadWorkflow(storage, browser, analyzer, replier)

    state = asyncio.run(
        workflow.run(
            "task-1", WorkflowConfig(dry_run=False), stop_event=stop_event
        )
    )

    assert state.status is WorkflowStatus.STOPPED
    assert state.comments_scanned == 1
    assert state.leads_found == 1
    assert replier.calls == []


def test_state_callback_observes_progress_before_workflow_finishes(tmp_path):
    async def exercise():
        release_search = asyncio.Event()
        search_started = asyncio.Event()

        class ControllableBrowser(FakeBrowserAdapter):
            async def search_posts(self, keyword, limit):
                search_started.set()
                await release_search.wait()
                return []

        workflow = FacebookLeadWorkflow(
            SQLiteLeadStorage(tmp_path / "leads.db"),
            ControllableBrowser(),
            FakeAnalyzerAdapter(),
            FakeReplyAdapter(),
        )
        updates = []
        task = asyncio.create_task(
            workflow.run(
                "task-1",
                WorkflowConfig(),
                on_state_update=lambda state: updates.append(state.model_copy(deep=True)),
            )
        )
        await search_started.wait()

        assert not task.done()
        assert [state.status for state in updates] == [WorkflowStatus.SEARCHING]

        release_search.set()
        final_state = await task
        return updates, final_state

    updates, final_state = asyncio.run(exercise())

    assert updates[-1].status is WorkflowStatus.DONE
    assert final_state.status is WorkflowStatus.DONE


def test_duplicate_successful_reply_is_not_sent_again(tmp_path):
    post = _post()
    comment = _comment(1, post)
    storage, _, _, replier, workflow = _workflow(
        tmp_path, [post], {post.url: [comment]}, {comment.comment_id: _analysis(comment)}
    )
    assert storage.record_reply("old-task", comment.comment_id, "Earlier", success=True)

    state = asyncio.run(workflow.run("task-1", WorkflowConfig(dry_run=False)))

    assert state.status is WorkflowStatus.DONE
    assert state.replies_sent == 0
    assert replier.calls == []
    assert storage.count_rows("reply_records") == 1




def test_state_callbacks_are_isolated_per_concurrent_run(tmp_path):
    async def exercise():
        workflow = FacebookLeadWorkflow(
            SQLiteLeadStorage(tmp_path / "leads.db"),
            FakeBrowserAdapter(),
            FakeAnalyzerAdapter(),
            FakeReplyAdapter(),
        )
        first_updates, second_updates = [], []
        await asyncio.gather(
            workflow.run("task-1", WorkflowConfig(), on_state_update=first_updates.append),
            workflow.run("task-2", WorkflowConfig(), on_state_update=second_updates.append),
        )
        return first_updates, second_updates

    first_updates, second_updates = asyncio.run(exercise())

    assert {state.task_id for state in first_updates} == {"task-1"}
    assert {state.task_id for state in second_updates} == {"task-2"}


def test_get_comments_and_analysis_errors_continue_to_later_posts(tmp_path):
    first, second, third = _post(1), _post(2), _post(3)
    second_comment = _comment(2, second)
    third_comment = _comment(3, third)

    class PerPostBrowser(FakeBrowserAdapter):
        async def get_comments(self, post, limit):
            if post.url == first.url:
                raise RuntimeError("comments unavailable")
            return await super().get_comments(post, limit)

    class PerPostAnalyzer(FakeAnalyzerAdapter):
        async def analyze_batch(self, comments):
            if comments[0].post_url == second.url:
                raise RuntimeError("analysis unavailable")
            return await super().analyze_batch(comments)

    storage = SQLiteLeadStorage(tmp_path / "leads.db")
    browser = PerPostBrowser(
        posts=[first, second, third],
        comments_by_post={second.url: [second_comment], third.url: [third_comment]},
    )
    analyzer = PerPostAnalyzer(results={third_comment.comment_id: _analysis(third_comment)})
    workflow = FacebookLeadWorkflow(storage, browser, analyzer, FakeReplyAdapter())

    state = asyncio.run(workflow.run("task-1", WorkflowConfig()))

    assert state.status is WorkflowStatus.DONE
    assert state.posts_scanned == 2
    assert state.comments_scanned == 2
    assert state.leads_found == 1
    assert state.failures == 2
    assert state.errors == [
        f"{first.url}: comments unavailable",
        f"{second.url}: analysis unavailable",
    ]
    assert storage.get_post("task-1", first.url)["scan_status"] == "error"
    assert storage.get_post("task-1", second.url)["scan_status"] == "error"
    assert storage.get_post("task-1", third.url)["scan_status"] == "done"


def test_concurrent_workflows_invoke_replier_once_per_comment_account(tmp_path):
    async def exercise():
        post = _post()
        comment = _comment(1, post)
        storage = SQLiteLeadStorage(tmp_path / "leads.db")
        browser = FakeBrowserAdapter(posts=[post], comments_by_post={post.url: [comment]})
        analyzer = FakeAnalyzerAdapter(results={comment.comment_id: _analysis(comment)})
        replier = FakeReplyAdapter()
        first = FacebookLeadWorkflow(storage, browser, analyzer, replier)
        second = FacebookLeadWorkflow(storage, browser, analyzer, replier)
        await asyncio.gather(
            first.run("task-1", WorkflowConfig(dry_run=False)),
            second.run("task-2", WorkflowConfig(dry_run=False)),
        )
        return replier.calls

    assert asyncio.run(exercise()) == [("comment-1", "你好")]


def test_unrecoverable_task_setup_error_returns_failed_state(tmp_path):
    class BrokenStorage(SQLiteLeadStorage):
        def create_task(self, task_id, config):
            raise RuntimeError("storage unavailable")

    workflow = FacebookLeadWorkflow(
        BrokenStorage(tmp_path / "leads.db"),
        FakeBrowserAdapter(),
        FakeAnalyzerAdapter(),
        FakeReplyAdapter(),
    )

    state = asyncio.run(workflow.run("task-1", WorkflowConfig()))

    assert state.status is WorkflowStatus.FAILED
    assert state.failures == 1
    assert state.errors == ["storage unavailable"]
