import asyncio

from src.facebook_leads.facebook.comments import (
    count_comment_candidates,
    expand_comments,
    extract_comment_author,
    extract_comments,
    find_comment_root,
    make_comment_fingerprint,
    scroll_comment_container,
    wait_for_comments_loaded,
)
from src.facebook_leads.facebook.comments import CommentRecord


class FakeButton:
    def __init__(self, page, changes=True):
        self.page = page
        self.changes = changes

    async def click(self, timeout=None):
        self.page.clicks += 1
        if self.changes:
            self.page.comment_dom_count += 1


class FakePage:
    def __init__(self, buttons=None, comment_records=None, panel_records=None, roots=None):
        self.buttons = list(buttons or [])
        self.comment_records = comment_records or []
        self.panel_records = panel_records or []
        self.roots = roots or []
        self.comment_dom_count = len(self.comment_records)
        self.clicks = 0
        self.panel_opens = 0

    async def next_more_comments_button(self):
        if self.buttons:
            return self.buttons.pop(0)
        return None

    async def open_comments_panel(self):
        self.panel_opens += 1
        if not self.panel_records:
            return False
        self.comment_records = self.panel_records
        self.comment_dom_count = len(self.comment_records)
        return True

    async def wait_for_timeout(self, ms):
        return None


class WaitingPage(FakePage):
    def __init__(self, delayed_records_after=0):
        super().__init__()
        self.delayed_records_after = delayed_records_after
        self.waits = 0

    async def wait_for_timeout(self, ms):
        self.waits += 1
        if self.waits >= self.delayed_records_after:
            self.comment_records = [
                {
                    "comment_id": "1",
                    "author_name": "John",
                    "author_url": None,
                    "text": "How much?",
                    "timestamp_text": None,
                    "comment_url": None,
                    "is_reply": False,
                    "parent_comment_id": None,
                }
            ]


class FakeRoot:
    def __init__(self, root_type, comment_records=None, candidate_count=None, growth=None):
        self.root_type = root_type
        self.comment_records = comment_records or []
        self.candidate_count = candidate_count if candidate_count is not None else len(self.comment_records)
        self.growth = list(growth or [])
        self.scroll_calls = 0

    async def scroll_comment_container_once(self):
        self.scroll_calls += 1
        if self.growth:
            self.candidate_count = self.growth.pop(0)
        return {
            "scroll_top": self.scroll_calls * 100,
            "scroll_height": 1000,
            "client_height": 500,
            "scrolled": True,
        }


def test_comment_expand_respects_max_expand_clicks():
    page = FakePage()
    page.buttons = [FakeButton(page) for _ in range(5)]

    result = asyncio.run(expand_comments(page, max_expand_clicks=2))

    assert result["expanded_comment_clicks"] == 2
    assert page.clicks == 2


def test_comment_expand_stops_after_consecutive_no_dom_changes():
    page = FakePage()
    page.buttons = [FakeButton(page, changes=False) for _ in range(5)]

    result = asyncio.run(expand_comments(page, max_expand_clicks=20))

    assert result["expanded_comment_clicks"] == 3
    assert result["stopped_after_unchanged_rounds"] is True


def test_comment_expand_opens_collapsed_comment_panel_before_counting():
    page = FakePage(
        panel_records=[
            {
                "comment_id": "1",
                "author_name": "John",
                "author_url": None,
                "text": "Interested",
                "timestamp_text": None,
                "comment_url": None,
                "is_reply": False,
                "parent_comment_id": None,
            }
        ]
    )

    result = asyncio.run(expand_comments(page, max_expand_clicks=0))

    assert result["opened_comment_panel"] is True
    assert result["final_comment_dom_count"] == 1
    assert page.panel_opens == 1


def test_find_comment_root_uses_page_when_page_has_comments():
    page = FakePage(comment_records=[{"text": "PM"}])

    root = asyncio.run(find_comment_root(page))

    assert root.root is page
    assert root.root_type == "page"


def test_find_comment_root_prefers_dialog_with_comments():
    page = FakePage(roots=[FakeRoot("page", candidate_count=0), FakeRoot("dialog", candidate_count=2)])

    root = asyncio.run(find_comment_root(page))

    assert root.root_type == "dialog"


def test_find_comment_root_chooses_comment_dialog_from_multiple_dialogs():
    page = FakePage(roots=[FakeRoot("dialog", candidate_count=0), FakeRoot("dialog", candidate_count=4)])

    root = asyncio.run(find_comment_root(page))

    assert root.metadata["candidate_count"] == 4


def test_find_comment_root_supports_overlay_fallback():
    page = FakePage(roots=[FakeRoot("overlay", candidate_count=1), FakeRoot("page", candidate_count=0)])

    root = asyncio.run(find_comment_root(page))

    assert root.root_type == "overlay"


def test_wait_for_comments_loaded_relocates_after_stale_empty_root():
    page = WaitingPage(delayed_records_after=2)

    count = asyncio.run(wait_for_comments_loaded(page, timeout_ms=3000, min_count=1))

    assert count == 1
    assert page.waits == 2


def test_wait_for_comments_loaded_times_out():
    page = WaitingPage(delayed_records_after=999)

    count = asyncio.run(wait_for_comments_loaded(page, timeout_ms=500, min_count=1))

    assert count == 0


def test_scroll_comment_container_records_growth_and_stops_after_no_growth():
    root = FakeRoot("nested_scroll_container", candidate_count=1, growth=[2, 2, 2])
    page = FakePage(roots=[root])

    result = asyncio.run(scroll_comment_container(page, max_rounds=5))

    assert result["rounds"][0]["before_count"] == 1
    assert result["rounds"][0]["after_count"] == 2
    assert len(result["rounds"]) == 3


def test_extract_comments_uses_supplied_root():
    page = FakePage(comment_records=[{"author_name": "Wrong", "text": "Ignore"}])
    root = FakeRoot(
        "dialog",
        comment_records=[
            {
                "comment_id": "1",
                "author_name": "Right",
                "author_url": None,
                "text": "PM",
                "timestamp_text": None,
                "comment_url": None,
                "is_reply": False,
                "parent_comment_id": None,
            }
        ],
    )

    comments = asyncio.run(extract_comments(page, "https://www.facebook.com/reel/1", root=root))

    assert len(comments) == 1
    assert comments[0].author_name == "Right"
    assert comments[0].text == "PM"


def test_extract_comments_falls_back_to_page_root():
    page = FakePage(
        comment_records=[
            {
                "comment_id": "1",
                "author_name": "John",
                "author_url": None,
                "text": "Yes",
                "timestamp_text": None,
                "comment_url": None,
                "is_reply": False,
                "parent_comment_id": None,
            }
        ]
    )

    comments = asyncio.run(extract_comments(page, "https://www.facebook.com/reel/1"))

    assert len(comments) == 1
    assert comments[0].text == "Yes"


def test_panel_open_does_not_touch_reply_or_send_when_comments_already_present():
    page = FakePage(comment_records=[{"author_name": "John", "text": "Interested"}])

    result = asyncio.run(expand_comments(page))

    assert result["comment_panel"]["attempted"] is False
    assert page.panel_opens == 0


def test_extract_comments_parses_missing_fields_without_crashing_and_dedupes():
    records = [
        {
            "comment_id": None,
            "author_name": "John",
            "author_url": None,
            "text": "How much?",
            "timestamp_text": None,
            "comment_url": None,
            "is_reply": False,
            "parent_comment_id": None,
        },
        {
            "comment_id": None,
            "author_name": "John",
            "author_url": None,
            "text": "How much?",
            "timestamp_text": None,
            "comment_url": None,
            "is_reply": False,
            "parent_comment_id": None,
        },
        {
            "comment_id": "2",
            "author_name": None,
            "author_url": None,
            "text": "Interested",
            "timestamp_text": "2h",
            "comment_url": None,
            "is_reply": True,
            "parent_comment_id": "1",
        },
    ]
    page = FakePage(comment_records=records)

    comments = asyncio.run(extract_comments(page, "https://www.facebook.com/a/posts/1"))

    assert len(comments) == 2
    assert comments[0].author_name == "John"
    assert comments[0].timestamp_text is None
    assert comments[1].author_name is None
    assert comments[1].is_reply is True


def test_extract_comment_author_keeps_username_profile_link():
    author = extract_comment_author(
        CommentRecord(
            author_name="Justin Kwoh",
            author_url="https://www.facebook.com/justin.kwoh",
        ),
        raw_text="Justin Kwoh\nHow much?",
    )

    assert author.author_name == "Justin Kwoh"
    assert author.author_url == "https://www.facebook.com/justin.kwoh"
    assert author.strategy == "profile_anchor"


def test_extract_comment_author_keeps_profile_php_link():
    author = extract_comment_author(
        CommentRecord(
            author_name="Chris Tiong",
            author_url="https://www.facebook.com/profile.php?id=123",
        ),
        raw_text="Chris Tiong\nGlb200 price please?",
    )

    assert author.author_name == "Chris Tiong"
    assert author.author_url == "https://www.facebook.com/profile.php?id=123"


def test_extract_comments_keeps_author_url_with_comment_id_separate_from_comment_url():
    page = FakePage(
        comment_records=[
            {
                "comment_id": None,
                "author_name": "Melvin Liew",
                "author_url": "https://www.facebook.com/melvin.liew?comment_id=101",
                "text": "Melvin Liew\nPm price for BMW 218I",
                "timestamp_text": None,
                "comment_url": None,
                "is_reply": False,
                "parent_comment_id": None,
            }
        ]
    )

    comments = asyncio.run(extract_comments(page, "https://www.facebook.com/reel/1"))

    assert comments[0].author_name == "Melvin Liew"
    assert comments[0].author_url == "https://www.facebook.com/melvin.liew?comment_id=101"
    assert comments[0].comment_id == "101"
    assert comments[0].comment_url is None
    assert comments[0].text == "Pm price for BMW 218I"
    assert comments[0].direct_comment_url == "https://www.facebook.com/reel/1?comment_id=101"


def test_extract_comments_uses_raw_text_first_line_author_fallback_and_cleans_body():
    page = FakePage(
        comment_records=[
            {
                "comment_id": "c1",
                "author_name": None,
                "author_url": None,
                "text": "Justin Kwoh\nWhat are the other charges like waxing and vacuum? Need buy package?",
                "timestamp_text": None,
                "comment_url": "https://www.facebook.com/reel/1?comment_id=c1",
                "is_reply": False,
                "parent_comment_id": None,
            }
        ]
    )

    comments = asyncio.run(extract_comments(page, "https://www.facebook.com/reel/1"))

    assert comments[0].author_name == "Justin Kwoh"
    assert comments[0].author_extract_strategy == "raw_text_first_line"
    assert comments[0].text == "What are the other charges like waxing and vacuum? Need buy package?"
    assert comments[0].comment_id == "c1"
    assert comments[0].direct_comment_url == "https://www.facebook.com/reel/1?comment_id=c1"


def test_raw_text_first_line_question_is_not_treated_as_author():
    page = FakePage(
        comment_records=[
            {
                "comment_id": "c1",
                "author_name": None,
                "author_url": None,
                "text": "How much?\nDo you deliver?",
                "timestamp_text": None,
                "comment_url": None,
                "is_reply": False,
                "parent_comment_id": None,
            }
        ]
    )

    comments = asyncio.run(extract_comments(page, "https://www.facebook.com/reel/1"))

    assert comments[0].author_name is None
    assert comments[0].text == "How much?\nDo you deliver?"


def test_raw_text_pm_is_not_treated_as_author():
    page = FakePage(
        comment_records=[
            {
                "comment_id": "c1",
                "author_name": None,
                "author_url": None,
                "text": "PM\nPlease send details",
                "timestamp_text": None,
                "comment_url": None,
                "is_reply": False,
                "parent_comment_id": None,
            }
        ]
    )

    comments = asyncio.run(extract_comments(page, "https://www.facebook.com/reel/1"))

    assert comments[0].author_name is None
    assert comments[0].text == "PM\nPlease send details"


def test_comment_fingerprint_is_stable():
    first = make_comment_fingerprint("url", "Author", "Text", "1h")
    second = make_comment_fingerprint("url", "Author", "Text", "1h")

    assert first == second
    assert len(first) == 64
