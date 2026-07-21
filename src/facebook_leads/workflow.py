from __future__ import annotations

import asyncio
from collections.abc import Callable

from .models import WorkflowConfig, WorkflowState, WorkflowStatus
from .storage import SQLiteLeadStorage


class FacebookLeadWorkflow:
    def __init__(self, storage, browser, analyzer, replier):
        self.storage: SQLiteLeadStorage = storage
        self.browser = browser
        self.analyzer = analyzer
        self.replier = replier

    async def run(
        self,
        task_id: str,
        config: WorkflowConfig,
        stop_event: asyncio.Event | None = None,
        on_state_update: Callable[[WorkflowState], None] | None = None,
    ) -> WorkflowState:
        state = WorkflowState(task_id=task_id, keyword=config.keyword)
        stop_event = stop_event or asyncio.Event()
        try:
            self.storage.create_task(task_id, config)
            if self._stop_if_requested(state, stop_event, on_state_update):
                return state
            self._transition(state, WorkflowStatus.SEARCHING, on_state_update)
            posts = await self.browser.search_posts(config.keyword, config.max_posts)
            state.posts_found = len(posts)
            if self._stop_if_requested(state, stop_event, on_state_update):
                return state

            self._transition(state, WorkflowStatus.COLLECTING_POSTS, on_state_update)
            for post in posts:
                if self._stop_if_requested(state, stop_event, on_state_update):
                    return state
                self.storage.save_post(task_id, post)
                state.current_post = post.url
                self._transition(state, WorkflowStatus.SCANNING_POST, on_state_update)
                try:
                    self._transition(state, WorkflowStatus.EXTRACTING_COMMENTS, on_state_update)
                    comments = await self.browser.get_comments(post, config.max_comments_per_post)
                    for comment in comments:
                        self.storage.save_comment(task_id, comment)
                    state.posts_scanned += 1
                    state.comments_scanned += len(comments)
                    if self._stop_if_requested(state, stop_event, on_state_update):
                        return state

                    if comments:
                        self._transition(state, WorkflowStatus.ANALYZING, on_state_update)
                        analyses = await self.analyzer.analyze_batch(comments)
                        analyses_by_id = {analysis.comment_id: analysis for analysis in analyses}
                        for analysis in analyses:
                            self.storage.save_lead(task_id, analysis)
                            if analysis.is_lead and analysis.score >= config.lead_threshold:
                                state.leads_found += 1
                        if self._stop_if_requested(state, stop_event, on_state_update):
                            return state

                        if not config.dry_run:
                            for comment in comments:
                                if state.replies_sent >= config.max_replies:
                                    break
                                analysis = analyses_by_id.get(comment.comment_id)
                                if not analysis or not (
                                    analysis.is_lead and analysis.score >= config.lead_threshold
                                ):
                                    continue
                                if self._stop_if_requested(state, stop_event, on_state_update):
                                    return state
                                if not self.storage.claim_reply(
                                    task_id, comment.comment_id, config.account_id, config.reply_text
                                ):
                                    continue
                                self._transition(state, WorkflowStatus.REPLYING, on_state_update)
                                try:
                                    success = await self.replier.reply(comment, config.reply_text)
                                except Exception as exc:
                                    success = False
                                    reply_error = str(exc)
                                else:
                                    reply_error = None if success else f"Reply failed for {comment.comment_id}"
                                self.storage.finalize_reply(
                                    task_id,
                                    comment.comment_id,
                                    config.account_id,
                                    success,
                                    reply_error,
                                )
                                if success:
                                    state.replies_sent += 1
                                else:
                                    state.failures += 1
                                    state.errors.append(reply_error or "Reply failed")
                                self._persist_and_notify(state, on_state_update)
                                if self._stop_if_requested(state, stop_event, on_state_update):
                                    return state
                    self.storage.update_post_scan(task_id, post.url, "done")
                except Exception as exc:
                    message = f"{post.url}: {exc}"
                    state.failures += 1
                    state.errors.append(message)
                    self.storage.update_post_scan(task_id, post.url, "error", str(exc))
                    self._persist_and_notify(state, on_state_update)
                    continue

            state.current_post = None
            self._transition(state, WorkflowStatus.VERIFYING, on_state_update)
            self._transition(state, WorkflowStatus.DONE, on_state_update)
        except Exception as exc:
            state.failures += 1
            state.errors.append(str(exc))
            self._transition(state, WorkflowStatus.FAILED, on_state_update)
        return state

    def _stop_if_requested(
        self,
        state: WorkflowState,
        stop_event: asyncio.Event,
        on_state_update: Callable[[WorkflowState], None] | None,
    ) -> bool:
        if not stop_event.is_set():
            return False
        self._transition(state, WorkflowStatus.STOPPED, on_state_update)
        return True

    def _transition(
        self,
        state: WorkflowState,
        status: WorkflowStatus,
        on_state_update: Callable[[WorkflowState], None] | None,
    ) -> None:
        state.transition_to(status)
        self._persist_and_notify(state, on_state_update)

    def _persist_and_notify(
        self,
        state: WorkflowState,
        on_state_update: Callable[[WorkflowState], None] | None,
    ) -> None:
        self.storage.update_task_state(state)
        if on_state_update:
            on_state_update(state.model_copy(deep=True))
