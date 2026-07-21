from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .labels import content_type_label, intent_category_label, intent_level_label


LeadIntentLevel = Literal["high", "medium", "low", "none"]


@dataclass(frozen=True)
class IntentMatch:
    keyword: str
    normalized_keyword: str
    category: str
    language: str
    weight: int
    matched_text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LeadCandidate:
    comment_fingerprint: str
    comment_id: str | None
    author_name: str | None
    author_url: str | None
    author_extract_strategy: str | None
    comment_text: str | None
    timestamp_text: str | None
    comment_url: str | None
    direct_comment_url: str | None
    comment_id_source: str | None
    source_content_url: str
    source_discovered_url: str | None
    source_final_url: str | None
    source_content_type: str | None
    source_text_preview: str | None
    source_author_name: str | None
    intent_score: int
    intent_level: LeadIntentLevel
    matched_keywords: list[IntentMatch] = field(default_factory=list)
    matched_categories: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    is_false_positive: bool = False
    false_positive_reason: str | None = None
    comment_locator_data: dict[str, Any] = field(default_factory=dict)
    rule_intent_score: int | None = None
    rule_intent_level: str | None = None
    rule_matched_keywords: list[str] = field(default_factory=list)
    rule_matched_categories: list[str] = field(default_factory=list)
    llm_review: dict[str, Any] | None = None
    llm_review_status: str = "disabled"
    final_is_lead: bool | None = None
    final_intent_level: str | None = None
    final_intent_types: list[str] = field(default_factory=list)
    final_reason_zh: str | None = None
    final_suggested_reply: str | None = None
    decision_source: str = "rule"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["matched_keywords"] = [item.to_dict() for item in self.matched_keywords]
        data["intent_level_label"] = intent_level_label(self.intent_level)
        data["matched_category_labels"] = [
            intent_category_label(category) for category in self.matched_categories
        ]
        data["source_content_type_label"] = content_type_label(self.source_content_type)
        return data


@dataclass
class ContentLeadSummary:
    source_content_url: str
    discovered_url: str | None
    final_url: str | None
    content_type: str | None
    text_preview: str | None
    author_name: str | None
    scanned_comment_count: int = 0
    text_comment_count: int = 0
    lead_candidate_count: int = 0
    high_intent_count: int = 0
    medium_intent_count: int = 0
    low_intent_count: int = 0
    leads: list[LeadCandidate] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["leads"] = [item.to_dict() for item in self.leads]
        data["content_type_label"] = content_type_label(self.content_type)
        return data


@dataclass
class LeadScanReport:
    keyword: str | None
    generated_at: str
    scanned_content_count: int
    scanned_comment_count: int
    text_comment_count: int
    lead_candidate_count: int
    high_intent_count: int
    medium_intent_count: int
    low_intent_count: int
    contents: list[ContentLeadSummary] = field(default_factory=list)
    timing: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    llm_review: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "keyword": self.keyword,
            "generated_at": self.generated_at,
            "scanned_content_count": self.scanned_content_count,
            "scanned_comment_count": self.scanned_comment_count,
            "text_comment_count": self.text_comment_count,
            "lead_candidate_count": self.lead_candidate_count,
            "high_intent_count": self.high_intent_count,
            "medium_intent_count": self.medium_intent_count,
            "low_intent_count": self.low_intent_count,
            "contents": [item.to_dict() for item in self.contents],
            "timing": self.timing,
            "diagnostics": self.diagnostics,
            "llm_review": self.llm_review,
        }
