import ast
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from src.facebook_leads.adapters import FakeAnalyzerAdapter, FakeBrowserAdapter, FakeReplyAdapter
from src.facebook_leads.models import CommentItem, LeadAnalysisResult, PostItem, WorkflowConfig, WorkflowStatus
from src.webui.components.facebook_leads_tab import (
    DEFAULT_RESULTS,
    RESULT_COLUMNS,
    FacebookLeadsTabController,
    state_to_display,
)



def test_interface_preserves_existing_tabs_and_adds_facebook_leads():
    interface_path = Path(__file__).parents[2] / "src/webui/interface.py"
    source = interface_path.read_text(encoding="utf-8")
    labels = [
        node.args[0].value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "TabItem"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    ]

    assert labels == [
        "⚙️ Agent Settings",
        "🌐 Browser Settings",
        "🤖 Run Agent",
        "🎁 Agent Marketplace",
        "Facebook Leads",
        "📁 Load & Save Config",
        "Deep Research",
    ]


def test_phase_two_code_does_not_include_real_browser_or_facebook_operations():
    project_root = Path(__file__).parents[2]
    phase_two_paths = [
        project_root / "src/facebook_leads/models.py",
        project_root / "src/facebook_leads/storage.py",
        project_root / "src/facebook_leads/workflow.py",
        project_root / "src/facebook_leads/adapters.py",
        project_root / "src/webui/components/facebook_leads_tab.py",
    ]
    forbidden_snippets = [
        "browser_use",
        "playwright",
        "facebook.com",
        ".goto(",
        ".locator(",
        "BrowserUseAgent",
    ]

    for path in phase_two_paths:
        source = path.read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            assert snippet not in source


def test_display_defaults_match_workflow_config():
    config = WorkflowConfig()

    assert config.model_dump() == {
        "keyword": "AI video",
        "max_posts": 10,
        "max_comments_per_post": 20,
        "lead_threshold": 75,
        "max_replies": 1,
        "reply_text": "你好",
        "target_customer_description": config.target_customer_description,
        "account_id": "default",
        "dry_run": True,
    }
    assert RESULT_COLUMNS == [
        "post_url",
        "author",
        "comment_text",
        "lead_score",
        "lead_reason",
        "lead_category",
        "reply_status",
        "error",
    ]
    assert DEFAULT_RESULTS == []


def test_state_to_display_exposes_progress_and_runtime():
    started_at = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    state = type(
        "State",
        (),
        {
            "status": WorkflowStatus.ANALYZING,
            "current_post": "https://example.test/post-1",
            "posts_found": 3,
            "posts_scanned": 1,
            "comments_scanned": 8,
            "leads_found": 2,
            "replies_sent": 0,
            "failures": 1,
            "started_at": started_at,
            "finished_at": None,
        },
    )()

    display = state_to_display(
        state, now=datetime(2026, 7, 20, 10, 0, 5, tzinfo=timezone.utc)
    )

    assert display == {
        "task_status": "ANALYZING",
        "current_stage": "ANALYZING",
        "current_post": "https://example.test/post-1",
        "posts_found": 3,
        "posts_scanned": 1,
        "comments_scanned": 8,
        "leads": 2,
        "replies": 0,
        "failures": 1,
        "start_time": "2026-07-20 10:00:00 UTC",
        "runtime": "5.0s",
    }


def test_start_streams_progress_before_workflow_finishes(tmp_path):
    async def exercise():
        release_search = asyncio.Event()
        search_started = asyncio.Event()

        class ControllableBrowser(FakeBrowserAdapter):
            async def search_posts(self, keyword, limit):
                search_started.set()
                await release_search.wait()
                return []

        controller = FacebookLeadsTabController(
            storage_path=tmp_path / "leads.db",
            browser=ControllableBrowser(),
            poll_interval=0,
        )
        stream = controller.start(WorkflowConfig())
        first = await anext(stream)
        pending_update = asyncio.create_task(anext(stream))
        await search_started.wait()
        second = await asyncio.wait_for(pending_update, timeout=1)

        assert first["current_stage"] == "SEARCHING"
        assert second["current_stage"] == "SEARCHING"
        assert controller.current_task is not None
        assert not controller.current_task.done()

        release_search.set()
        remaining = [update async for update in stream]
        return remaining

    remaining = asyncio.run(exercise())

    assert remaining[-1]["current_stage"] == "DONE"


def test_start_streams_fake_workflow_state_and_results(tmp_path):
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
        text="多少钱？",
        reply_target_hint="reply",
    )
    analysis = LeadAnalysisResult(
        comment_id=comment.comment_id,
        is_lead=True,
        score=90,
        reason="Asked about price",
        category="price",
    )
    replier = FakeReplyAdapter()
    controller = FacebookLeadsTabController(
        storage_path=tmp_path / "leads.db",
        browser=FakeBrowserAdapter(posts=[post], comments_by_post={post.url: [comment]}),
        analyzer=FakeAnalyzerAdapter(results={comment.comment_id: analysis}),
        replier=replier,
        poll_interval=0,
    )

    async def collect_updates():
        return [
            update
            async for update in controller.start(
                WorkflowConfig(keyword="AI video", dry_run=True)
            )
        ]

    updates = asyncio.run(collect_updates())

    assert [update["current_stage"] for update in updates] == [
        "SEARCHING",
        "SEARCHING",
        "COLLECTING_POSTS",
        "SCANNING_POST",
        "EXTRACTING_COMMENTS",
        "ANALYZING",
        "VERIFYING",
        "DONE",
    ]
    assert updates[0]["start_enabled"] is False
    assert updates[0]["stop_enabled"] is True
    assert updates[0]["clear_enabled"] is False
    assert updates[-1]["start_enabled"] is True
    assert updates[-1]["stop_enabled"] is False
    assert updates[-1]["clear_enabled"] is True
    assert updates[-1]["task_status"] == "DONE"
    assert updates[-1]["posts_found"] == 1
    assert updates[-1]["comments_scanned"] == 1
    assert updates[-1]["leads"] == 1
    assert updates[-1]["results"] == [[
        post.url,
        "Alice",
        "多少钱？",
        90,
        "Asked about price",
        "price",
        "dry_run",
        "",
    ]]
    assert replier.calls == []


def test_stop_sets_the_current_stop_event(tmp_path):
    controller = FacebookLeadsTabController(storage_path=tmp_path / "leads.db")
    controller.stop_event = asyncio.Event()

    update = asyncio.run(controller.stop())

    assert controller.stop_event.is_set()
    assert update["task_status"] == "STOPPING"
    assert update["start_enabled"] is False
    assert update["stop_enabled"] is False
    assert update["clear_enabled"] is False


def test_clear_stops_active_work_and_resets_safely(tmp_path):
    controller = FacebookLeadsTabController(storage_path=tmp_path / "leads.db")
    controller.stop_event = asyncio.Event()

    update = asyncio.run(controller.clear())

    assert controller.stop_event.is_set()
    assert update["task_status"] == "IDLE"
    assert update["results"] == []
    assert update["current_post"] == ""
    assert update["runtime"] == "0.0s"
    assert update["start_enabled"] is True
    assert update["stop_enabled"] is False
    assert update["clear_enabled"] is True


def test_clear_waits_for_pending_task_before_resetting(tmp_path):
    controller = FacebookLeadsTabController(storage_path=tmp_path / "leads.db")

    async def exercise_clear():
        release = asyncio.Event()
        finished = asyncio.Event()

        async def pending_work():
            await release.wait()
            finished.set()

        controller.stop_event = asyncio.Event()
        controller.current_task = asyncio.create_task(pending_work())
        clear_task = asyncio.create_task(controller.clear())
        await asyncio.sleep(0)

        assert controller.stop_event.is_set()
        assert not clear_task.done()
        assert not finished.is_set()

        release.set()
        update = await clear_task
        return update, finished.is_set(), controller.current_task

    update, finished, current_task = asyncio.run(exercise_clear())

    assert finished is True
    assert current_task is None
    assert update["task_status"] == "IDLE"




def test_double_start_is_excluded_before_first_yield(tmp_path):
    async def exercise():
        release = asyncio.Event()

        class BlockingBrowser(FakeBrowserAdapter):
            async def search_posts(self, keyword, limit):
                await release.wait()
                return []

        controller = FacebookLeadsTabController(
            storage_path=tmp_path / "leads.db", browser=BlockingBrowser(), poll_interval=0
        )
        first_stream = controller.start(WorkflowConfig())
        second_stream = controller.start(WorkflowConfig())
        first_pending = asyncio.create_task(anext(first_stream))
        second_pending = asyncio.create_task(anext(second_stream))
        first, second = await asyncio.gather(first_pending, second_pending)

        assert sorted([first["current_stage"], second["current_stage"]]) == [
            "RUNNING",
            "SEARCHING",
        ]
        assert controller.current_task is not None
        release.set()
        await first_stream.aclose()
        await second_stream.aclose()
        await controller.clear()

    asyncio.run(exercise())


def test_stop_preserves_last_display_progress(tmp_path):
    async def exercise():
        controller = FacebookLeadsTabController(storage_path=tmp_path / "leads.db")
        controller.last_display = {
            **controller.last_display,
            "task_status": "ANALYZING",
            "current_stage": "ANALYZING",
            "posts_found": 3,
            "posts_scanned": 2,
            "comments_scanned": 7,
            "leads": 4,
            "failures": 1,
        }
        return await controller.stop()

    update = asyncio.run(exercise())

    assert update["task_status"] == "STOPPING"
    assert update["posts_found"] == 3
    assert update["posts_scanned"] == 2
    assert update["comments_scanned"] == 7
    assert update["leads"] == 4
    assert update["failures"] == 1


def test_results_include_only_persisted_processed_comments(tmp_path):
    first, second = [], []
    for number in (1, 2):
        post = PostItem(
            url=f"https://example.test/post-{number}",
            title="AI video",
            platform="facebook",
            discovered_at=datetime.now(timezone.utc),
        )
        comment = CommentItem(
            comment_id=f"comment-{number}",
            external_id=f"external-{number}",
            post_url=post.url,
            author=f"Author {number}",
            text=f"Lead {number}",
            reply_target_hint="reply",
        )
        analysis = LeadAnalysisResult(
            comment_id=comment.comment_id,
            is_lead=True,
            score=90,
            reason="intent",
            category="interest",
        )
        (first if number == 1 else second).extend([post, comment, analysis])

    controller = FacebookLeadsTabController(
        storage_path=tmp_path / "leads.db",
        browser=FakeBrowserAdapter(
            posts=[first[0], second[0]],
            comments_by_post={first[0].url: [first[1]], second[0].url: [second[1]]},
        ),
        analyzer=FakeAnalyzerAdapter(
            results={first[1].comment_id: first[2], second[1].comment_id: second[2]}
        ),
        poll_interval=0,
    )

    async def collect():
        return [update async for update in controller.start(WorkflowConfig(max_posts=1))]

    updates = asyncio.run(collect())

    assert len(updates[-1]["results"]) == 1
    assert updates[-1]["results"][0][0] == first[0].url
