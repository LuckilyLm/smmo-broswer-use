from __future__ import annotations

from collections.abc import Callable

from .models import CommentItem, LeadAnalysisResult, PostItem


class FakeBrowserAdapter:
    def __init__(
        self,
        posts: list[PostItem] | None = None,
        comments_by_post: dict[str, list[CommentItem]] | None = None,
        on_search: Callable[[], None] | None = None,
    ):
        self.posts = posts or []
        self.comments_by_post = comments_by_post or {}
        self.on_search = on_search
        self.search_calls: list[tuple[str, int]] = []
        self.comment_calls: list[tuple[str, int]] = []

    async def search_posts(self, keyword: str, limit: int) -> list[PostItem]:
        self.search_calls.append((keyword, limit))
        if self.on_search:
            self.on_search()
        return self.posts[:limit]

    async def get_comments(self, post: PostItem, limit: int) -> list[CommentItem]:
        self.comment_calls.append((post.url, limit))
        return self.comments_by_post.get(post.url, [])[:limit]


class FakeAnalyzerAdapter:
    def __init__(
        self,
        results: dict[str, LeadAnalysisResult] | None = None,
        error: Exception | None = None,
        on_batch: Callable[[], None] | None = None,
    ):
        self.results = results or {}
        self.error = error
        self.on_batch = on_batch
        self.batch_calls: list[list[str]] = []

    async def analyze_batch(
        self, comments: list[CommentItem]
    ) -> list[LeadAnalysisResult]:
        self.batch_calls.append([comment.comment_id for comment in comments])
        if self.error:
            raise self.error
        if self.on_batch:
            self.on_batch()
        return [
            self.results.get(
                comment.comment_id,
                LeadAnalysisResult(
                    comment_id=comment.comment_id,
                    is_lead=False,
                    score=0,
                    reason="No configured fake result",
                    category="other",
                ),
            )
            for comment in comments
        ]


class FakeReplyAdapter:
    def __init__(self, success: bool = True):
        self.success = success
        self.calls: list[tuple[str, str]] = []

    async def reply(self, comment: CommentItem, text: str) -> bool:
        self.calls.append((comment.comment_id, text))
        return self.success
