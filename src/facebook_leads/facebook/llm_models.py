from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


LLMIntentLevel = Literal["high", "medium", "low", "none"]
LLMReviewStatus = Literal["disabled", "success", "failed", "timeout", "missing"]

VALID_INTENT_LEVELS = {"high", "medium", "low", "none"}
VALID_INTENT_TYPES = {
    "price",
    "buy",
    "delivery",
    "location",
    "contact",
    "service",
    "product",
    "other",
}
HIGH_RISK_FLAGS = {"spam", "abusive", "sensitive", "possible_scam"}


@dataclass(frozen=True)
class LLMLeadReview:
    comment_fingerprint: str
    status: LLMReviewStatus
    is_lead: bool
    confidence: float
    intent_level: LLMIntentLevel
    intent_types: list[str] = field(default_factory=list)
    reason_zh: str = ""
    summary_zh: str = ""
    suggested_reply: str = ""
    reply_language: str = "en"
    should_reply: bool = False
    risk_flags: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReviewedLeadCandidate:
    lead: Any
    rule_intent_score: int
    rule_intent_level: str | None
    rule_matched_keywords: list[str]
    rule_matched_categories: list[str]
    llm_review: LLMLeadReview
    final_is_lead: bool
    final_intent_level: str | None
    final_intent_types: list[str]
    final_reason_zh: str | None
    final_suggested_reply: str | None
    decision_source: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if hasattr(self.lead, "to_dict"):
            data["lead"] = self.lead.to_dict()
        return data


def failed_review(comment_fingerprint: str, error: str, status: LLMReviewStatus = "failed") -> LLMLeadReview:
    return LLMLeadReview(
        comment_fingerprint=comment_fingerprint,
        status=status,
        is_lead=False,
        confidence=0.0,
        intent_level="none",
        should_reply=False,
        error=error,
    )


def disabled_review(comment_fingerprint: str) -> LLMLeadReview:
    return LLMLeadReview(
        comment_fingerprint=comment_fingerprint,
        status="disabled",
        is_lead=False,
        confidence=0.0,
        intent_level="none",
        should_reply=False,
    )
