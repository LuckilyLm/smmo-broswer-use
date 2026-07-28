from __future__ import annotations

import re
import unicodedata
from typing import Any

from .intent_keywords import (
    CATEGORY_WEIGHTS,
    FALSE_POSITIVE_SINGLETONS,
    INTENT_KEYWORDS,
    MACRO_PRICE_CONTEXT,
    STRONG_INTENT_PHRASES,
)
from .intent_models import IntentMatch, LeadCandidate, LeadIntentLevel
from .models import FacebookComment


def normalize_comment_text(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.lower().strip()
    normalized = re.sub(r"[\u2018\u2019]", "'", normalized)
    normalized = re.sub(r"[\u201c\u201d]", '"', normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


class LeadIntentClassifier:
    def __init__(self, custom_positive_keywords: list[str] | tuple[str, ...] | None = None) -> None:
        self.custom_positive_keywords = tuple(str(item).strip() for item in (custom_positive_keywords or []) if str(item).strip())

    def classify_comment(
        self,
        comment: FacebookComment,
        source_metadata: dict[str, Any] | None = None,
    ) -> LeadCandidate | None:
        source_metadata = source_metadata or {}
        text = comment.text or ""
        normalized_text = normalize_comment_text(text)
        raw_matches = self._match_keywords(normalized_text)
        if not raw_matches:
            return None
        resolution = resolve_keyword_matches(raw_matches)
        matches = resolution["effective_matches"]

        categories = sorted({match.category for match in matches})
        score = sum(match.weight for match in matches)
        reasons = [f"{match.category}: {match.keyword}" for match in matches]
        false_positive, false_positive_reason = self._false_positive(normalized_text, matches)
        if false_positive:
            score = min(score, 1)
            reasons.append(false_positive_reason or "possible false positive")
        strong_hits = _strong_intent_hits(normalized_text, matches)
        strong_bonus = min(2 * len({match.category for match in strong_hits}), 2 * len(categories))
        if strong_hits and not false_positive:
            score += strong_bonus
            reasons.append("strong intent phrase: " + ", ".join(match.normalized_keyword for match in strong_hits))
        score_breakdown = {match.category: match.weight for match in matches}
        if strong_bonus:
            score_breakdown["strong_intent_bonus"] = strong_bonus
        score_breakdown["total"] = score

        level = score_to_level(score)
        if level == "none":
            return None

        return LeadCandidate(
            comment_fingerprint=comment.fingerprint,
            comment_id=comment.comment_id,
            author_name=comment.author_name,
            author_url=comment.author_url,
            author_extract_strategy=comment.author_extract_strategy,
            comment_text=comment.text,
            timestamp_text=comment.timestamp_text,
            comment_url=comment.comment_url,
            direct_comment_url=comment.direct_comment_url,
            comment_id_source=comment.comment_id_source,
            source_content_url=comment.source_content_url,
            source_discovered_url=source_metadata.get("discovered_url"),
            source_final_url=source_metadata.get("final_url") or comment.source_content_url,
            source_content_type=source_metadata.get("content_type"),
            source_text_preview=source_metadata.get("text_preview"),
            source_author_name=source_metadata.get("author_name"),
            intent_score=score,
            intent_level=level,
            matched_keywords=matches,
            matched_categories=categories,
            raw_matched_keywords=[match.normalized_keyword for match in raw_matches],
            effective_matched_keywords=[match.normalized_keyword for match in matches],
            deduplicated_keywords=[match.normalized_keyword for match in resolution["deduplicated_matches"]],
            score_breakdown=score_breakdown,
            reasons=reasons,
            is_false_positive=false_positive,
            false_positive_reason=false_positive_reason,
            comment_locator_data={
                "comment_id": comment.comment_id,
                "author_name": comment.author_name,
                "comment_text": comment.text,
                "source_content_url": comment.source_content_url,
                "direct_comment_url": comment.direct_comment_url,
            },
            rule_intent_score=score,
            rule_intent_level=level,
            rule_matched_keywords=[match.keyword for match in matches],
            rule_matched_categories=categories,
            llm_review_status="disabled",
            final_is_lead=True,
            final_intent_level=level,
            final_intent_types=[category.lower() for category in categories],
            decision_source="rule_only",
        )

    def _match_keywords(self, normalized_text: str) -> list[IntentMatch]:
        seen: set[tuple[str, str]] = set()
        matches: list[IntentMatch] = []
        for category, languages in INTENT_KEYWORDS.items():
            for language, keywords in languages.items():
                for keyword in keywords:
                    normalized_keyword = normalize_comment_text(keyword)
                    if (category, normalized_keyword) in seen:
                        continue
                    if not _phrase_matches(normalized_text, normalized_keyword):
                        continue
                    seen.add((category, normalized_keyword))
                    matches.append(
                        IntentMatch(
                            keyword=keyword,
                            normalized_keyword=normalized_keyword,
                            category=category,
                            language=language,
                            weight=CATEGORY_WEIGHTS[category],
                            matched_text=keyword,
                        )
                    )
        for keyword in self.custom_positive_keywords:
            normalized_keyword = normalize_comment_text(keyword)
            if not normalized_keyword or ("CONTACT", normalized_keyword) in seen:
                continue
            if not _phrase_matches(normalized_text, normalized_keyword):
                continue
            seen.add(("CONTACT", normalized_keyword))
            matches.append(
                IntentMatch(
                    keyword=keyword,
                    normalized_keyword=normalized_keyword,
                    category="CONTACT",
                    language="custom",
                    weight=CATEGORY_WEIGHTS["CONTACT"],
                    matched_text=keyword,
                )
            )
        return matches

    def _false_positive(self, normalized_text: str, matches: list[IntentMatch]) -> tuple[bool, str | None]:
        normalized_hits = {match.normalized_keyword for match in matches}
        if normalized_hits and normalized_hits <= FALSE_POSITIVE_SINGLETONS:
            return True, "singleton inventory word is not enough purchase intent"
        if any(match.category == "PRICE" for match in matches) and any(
            phrase in normalized_text for phrase in MACRO_PRICE_CONTEXT
        ):
            return True, "price term appears in broad market context"
        return False, None


def score_to_level(score: int) -> LeadIntentLevel:
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    if score >= 1:
        return "low"
    return "none"


def resolve_keyword_matches(matches: list[IntentMatch]) -> dict[str, list[IntentMatch]]:
    effective: list[IntentMatch] = []
    deduplicated: list[IntentMatch] = []
    by_category: dict[str, list[tuple[int, IntentMatch]]] = {}
    for index, match in enumerate(matches):
        by_category.setdefault(match.category, []).append((index, match))

    for _category, grouped in by_category.items():
        selected_indexes: set[int] = set()
        for index, match in grouped:
            if any(
                other_index != index and _keyword_contains(other.normalized_keyword, match.normalized_keyword)
                for other_index, other in grouped
            ):
                deduplicated.append(match)
                continue
            selected_indexes.add(index)
        if not selected_indexes and grouped:
            selected = sorted(
                grouped,
                key=lambda item: (-len(item[1].normalized_keyword), -item[1].weight, item[0]),
            )[0][0]
            selected_indexes.add(selected)
        effective.extend(match for index, match in grouped if index in selected_indexes)
    return {"raw_matches": matches, "effective_matches": effective, "deduplicated_matches": deduplicated}


def _strong_intent_hits(normalized_text: str, matches: list[IntentMatch]) -> list[IntentMatch]:
    hits = []
    seen_categories: set[str] = set()
    for match in matches:
        if match.category in seen_categories:
            continue
        if any(_keyword_contains(match.normalized_keyword, phrase) or _keyword_contains(phrase, match.normalized_keyword) for phrase in STRONG_INTENT_PHRASES if phrase in normalized_text):
            hits.append(match)
            seen_categories.add(match.category)
    return hits


def _keyword_contains(longer: str, shorter: str) -> bool:
    if longer == shorter:
        return True
    if _contains_cjk_or_non_word(longer) or _contains_cjk_or_non_word(shorter):
        return shorter in longer
    return re.search(rf"(?<![a-z0-9]){re.escape(shorter)}(?![a-z0-9])", longer, re.I) is not None


def _phrase_matches(text: str, phrase: str) -> bool:
    if not text or not phrase:
        return False
    if _contains_cjk_or_non_word(phrase):
        return phrase in text
    pattern = rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])"
    return re.search(pattern, text, re.I) is not None


def _contains_cjk_or_non_word(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)
