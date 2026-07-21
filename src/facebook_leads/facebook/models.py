from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


FacebookLoginState = Literal["logged_in", "logged_out", "checkpoint", "captcha", "unknown"]
FacebookContentType = Literal["post", "reel", "video", "unknown"]


@dataclass(frozen=True)
class FacebookContentCandidate:
    url: str
    content_type: FacebookContentType | None = None
    text_preview: str | None = None
    author_name: str | None = None
    discovered_from: str | None = None
    discovery_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FacebookComment:
    comment_id: str | None
    author_name: str | None
    author_url: str | None
    text: str | None
    timestamp_text: str | None
    comment_url: str | None
    is_reply: bool
    parent_comment_id: str | None
    source_content_url: str
    fingerprint: str
    direct_comment_url: str | None = None
    comment_id_source: str | None = None
    author_extract_strategy: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FacebookScanResult:
    success: bool
    stage: str
    keyword: str | None
    login_state: FacebookLoginState
    active_page_url: str | None
    contents: list[FacebookContentCandidate] = field(default_factory=list)
    comments: list[FacebookComment] = field(default_factory=list)
    timing: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    error_type: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "stage": self.stage,
            "keyword": self.keyword,
            "login_state": self.login_state,
            "active_page_url": self.active_page_url,
            "contents": [item.to_dict() for item in self.contents],
            "comments": [item.to_dict() for item in self.comments],
            "timing": self.timing,
            "diagnostics": self.diagnostics,
            "error_type": self.error_type,
            "error": self.error,
        }
