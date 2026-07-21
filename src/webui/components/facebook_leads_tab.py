from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator

from src.facebook_leads.adapters import (
    FakeAnalyzerAdapter,
    FakeBrowserAdapter,
    FakeReplyAdapter,
)
from src.facebook_leads.models import WorkflowConfig, WorkflowState
from src.facebook_leads.storage import SQLiteLeadStorage
from src.facebook_leads.workflow import FacebookLeadWorkflow

RESULT_COLUMNS = [
    "post_url",
    "author",
    "comment_text",
    "lead_score",
    "lead_reason",
    "lead_category",
    "reply_status",
    "error",
]
DEFAULT_RESULTS: list[list[Any]] = []
DISPLAY_KEYS = [
    "task_status",
    "current_stage",
    "current_post",
    "posts_found",
    "posts_scanned",
    "comments_scanned",
    "leads",
    "replies",
    "failures",
    "start_time",
    "runtime",
    "results",
    "start_enabled",
    "stop_enabled",
    "clear_enabled",
]


def _runtime_seconds(state: WorkflowState, now: datetime | None = None) -> float:
    end = state.finished_at or now or datetime.now(timezone.utc)
    return max(0.0, (end - state.started_at).total_seconds())


def state_to_display(
    state: WorkflowState, now: datetime | None = None
) -> dict[str, Any]:
    return {
        "task_status": state.status.value,
        "current_stage": state.status.value,
        "current_post": state.current_post or "",
        "posts_found": state.posts_found,
        "posts_scanned": state.posts_scanned,
        "comments_scanned": state.comments_scanned,
        "leads": state.leads_found,
        "replies": state.replies_sent,
        "failures": state.failures,
        "start_time": state.started_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "runtime": f"{_runtime_seconds(state, now):.1f}s",
    }


def empty_display() -> dict[str, Any]:
    return {
        "task_status": "IDLE",
        "current_stage": "IDLE",
        "current_post": "",
        "posts_found": 0,
        "posts_scanned": 0,
        "comments_scanned": 0,
        "leads": 0,
        "replies": 0,
        "failures": 0,
        "start_time": "",
        "runtime": "0.0s",
        "results": [],
        "start_enabled": True,
        "stop_enabled": False,
        "clear_enabled": True,
    }


class FacebookLeadsTabController:
    """Owns one local fake-only workflow run for the Gradio tab."""

    def __init__(
        self,
        storage_path: str | Path | None = None,
        browser: FakeBrowserAdapter | None = None,
        analyzer: FakeAnalyzerAdapter | None = None,
        replier: FakeReplyAdapter | None = None,
        poll_interval: float = 0.05,
    ):
        default_path = Path("data/facebook_leads.db")
        self.storage = SQLiteLeadStorage(storage_path or default_path)
        self.browser = browser or FakeBrowserAdapter()
        self.analyzer = analyzer or FakeAnalyzerAdapter()
        self.replier = replier or FakeReplyAdapter()
        self.workflow = FacebookLeadWorkflow(
            self.storage, self.browser, self.analyzer, self.replier
        )
        self.poll_interval = poll_interval
        self.stop_event: asyncio.Event | None = None
        self.current_task: asyncio.Task | None = None
        self._start_lock = asyncio.Lock()
        self.last_display = empty_display()

    async def start(
        self, config: WorkflowConfig
    ) -> AsyncGenerator[dict[str, Any], None]:
        duplicate_start = False
        async with self._start_lock:
            if self.current_task and not self.current_task.done():
                duplicate_start = True
                initial = {
                    **self.last_display,
                    "task_status": "RUNNING",
                    "current_stage": "RUNNING",
                }
            else:
                stop_event = asyncio.Event()
                task_id = str(uuid.uuid4())
                started_at = datetime.now(timezone.utc)
                updates: asyncio.Queue[WorkflowState] = asyncio.Queue()
                task = asyncio.create_task(
                    self.workflow.run(
                        task_id,
                        config,
                        stop_event,
                        on_state_update=updates.put_nowait,
                    )
                )
                self.stop_event = stop_event
                self.current_task = task
                initial = {
                    **empty_display(),
                    "task_status": "RUNNING",
                    "current_stage": "SEARCHING",
                    "start_time": started_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "start_enabled": False,
                    "stop_enabled": True,
                    "clear_enabled": False,
                }
                self.last_display = initial

        if duplicate_start:
            yield initial
            return

        try:
            yield initial
            while not task.done() or not updates.empty():
                try:
                    state = await asyncio.wait_for(
                        updates.get(), timeout=max(self.poll_interval, 0.001)
                    )
                except asyncio.TimeoutError:
                    continue
                update = {
                    **state_to_display(state),
                    "results": [],
                    "start_enabled": False,
                    "stop_enabled": True,
                    "clear_enabled": False,
                }
                if state.finished_at is not None:
                    update.update(
                        results=self._result_rows(task_id, config),
                        start_enabled=True,
                        stop_enabled=False,
                        clear_enabled=True,
                    )
                self.last_display = {**self.last_display, **update}
                yield self.last_display.copy()
            await task
        finally:
            if self.current_task is task:
                if not task.done():
                    stop_event.set()
                    await task
                self.current_task = None

    async def stop(self) -> dict[str, Any]:
        if self.stop_event is not None:
            self.stop_event.set()
        self.last_display = {
            **self.last_display,
            "task_status": "STOPPING",
            "current_stage": "STOPPING",
            "start_enabled": False,
            "stop_enabled": False,
            "clear_enabled": False,
        }
        return self.last_display.copy()

    async def clear(self) -> dict[str, Any]:
        if self.stop_event is not None:
            self.stop_event.set()
        task = self.current_task
        if task is not None and not task.done():
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self.current_task = None
        self.last_display = empty_display()
        return self.last_display.copy()

    def _result_rows(
        self, task_id: str, config: WorkflowConfig
    ) -> list[list[Any]]:
        return self.storage.result_rows(task_id, config.lead_threshold, config.dry_run)


def _display_values(update: dict[str, Any]) -> list[Any]:
    baseline = empty_display()
    baseline.update(update)
    return [baseline[key] for key in DISPLAY_KEYS]


def create_facebook_leads_tab(webui_manager) -> None:
    import gradio as gr

    defaults = WorkflowConfig()
    controller = FacebookLeadsTabController()
    webui_manager.fl_controller = controller

    with gr.Row():
        keyword = gr.Textbox(label="关键词", value=defaults.keyword)
        max_posts = gr.Number(label="最大帖子数", value=defaults.max_posts, precision=0)
        max_comments = gr.Number(
            label="每帖最大评论数", value=defaults.max_comments_per_post, precision=0
        )
    with gr.Row():
        lead_threshold = gr.Number(
            label="线索阈值", value=defaults.lead_threshold, precision=0
        )
        max_replies = gr.Number(
            label="最大回复数", value=defaults.max_replies, precision=0
        )
        dry_run = gr.Checkbox(label="Dry run", value=defaults.dry_run)
    reply_text = gr.Textbox(label="回复文本", value=defaults.reply_text)
    target_customer_description = gr.Textbox(
        label="目标客户描述",
        value=defaults.target_customer_description,
        lines=3,
    )
    with gr.Row():
        start_button = gr.Button("开始任务", variant="primary")
        stop_button = gr.Button("停止任务", variant="stop", interactive=False)
        clear_button = gr.Button("清空结果")

    with gr.Row():
        task_status = gr.Textbox(label="任务状态", value="IDLE", interactive=False)
        current_stage = gr.Textbox(label="当前阶段", value="IDLE", interactive=False)
        current_post = gr.Textbox(label="当前帖子", interactive=False)
    with gr.Row():
        posts_found = gr.Number(label="发现帖子", value=0, interactive=False)
        posts_scanned = gr.Number(label="扫描帖子", value=0, interactive=False)
        comments_scanned = gr.Number(label="扫描评论", value=0, interactive=False)
        leads = gr.Number(label="线索", value=0, interactive=False)
        replies = gr.Number(label="回复", value=0, interactive=False)
        failures = gr.Number(label="失败", value=0, interactive=False)
    with gr.Row():
        start_time = gr.Textbox(label="开始时间", interactive=False)
        runtime = gr.Textbox(label="运行时间", value="0.0s", interactive=False)
    results = gr.Dataframe(
        headers=RESULT_COLUMNS,
        value=DEFAULT_RESULTS,
        datatype=["str", "str", "str", "number", "str", "str", "str", "str"],
        interactive=False,
        label="线索结果",
    )

    components = {
        "keyword": keyword,
        "max_posts": max_posts,
        "max_comments_per_post": max_comments,
        "lead_threshold": lead_threshold,
        "max_replies": max_replies,
        "reply_text": reply_text,
        "target_customer_description": target_customer_description,
        "dry_run": dry_run,
        "start_button": start_button,
        "stop_button": stop_button,
        "clear_button": clear_button,
        "task_status": task_status,
        "current_stage": current_stage,
        "current_post": current_post,
        "posts_found": posts_found,
        "posts_scanned": posts_scanned,
        "comments_scanned": comments_scanned,
        "leads": leads,
        "replies": replies,
        "failures": failures,
        "start_time": start_time,
        "runtime": runtime,
        "results": results,
    }
    webui_manager.add_components("facebook_leads", components)
    outputs = [
        task_status,
        current_stage,
        current_post,
        posts_found,
        posts_scanned,
        comments_scanned,
        leads,
        replies,
        failures,
        start_time,
        runtime,
        results,
        start_button,
        stop_button,
        clear_button,
    ]

    def gradio_values(update: dict[str, Any]) -> list[Any]:
        values = _display_values(update)
        for index, key in enumerate(DISPLAY_KEYS):
            if key.endswith("_enabled"):
                values[index] = gr.update(interactive=values[index])
        return values

    async def start_handler(*values):
        config = WorkflowConfig(
            keyword=values[0],
            max_posts=int(values[1]),
            max_comments_per_post=int(values[2]),
            lead_threshold=int(values[3]),
            max_replies=int(values[4]),
            reply_text=values[5],
            target_customer_description=values[6],
            dry_run=values[7],
        )
        async for update in controller.start(config):
            yield gradio_values(update)

    async def stop_handler():
        update = await controller.stop()
        yield gradio_values(update)

    async def clear_handler():
        update = await controller.clear()
        yield gradio_values(update)

    inputs = [
        keyword,
        max_posts,
        max_comments,
        lead_threshold,
        max_replies,
        reply_text,
        target_customer_description,
        dry_run,
    ]
    start_button.click(start_handler, inputs=inputs, outputs=outputs)
    stop_button.click(stop_handler, inputs=None, outputs=outputs)
    clear_button.click(clear_handler, inputs=None, outputs=outputs)
