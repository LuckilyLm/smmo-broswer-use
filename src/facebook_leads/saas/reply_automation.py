from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ALLOWED_TEMPLATE_VARIABLES = {
    "whatsapp",
    "email",
    "website",
    "contact",
    "campaign_name",
    "keyword",
    "author_name",
}
PLACEHOLDER_RE = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass(frozen=True)
class MatchResult:
    matched: bool
    blocked_reason: str | None = None
    rule_id: str | None = None
    template_id: str | None = None
    matched_rule: str | None = None


def render_template(content: str, values: dict[str, Any]) -> str:
    if not content or not content.strip():
        raise ValueError("template_content_empty")
    if CONTROL_RE.search(content):
        raise ValueError("template_content_invalid")
    names = set(PLACEHOLDER_RE.findall(content))
    unknown = names - ALLOWED_TEMPLATE_VARIABLES
    if unknown:
        raise ValueError(f"unknown_template_variable:{sorted(unknown)[0]}")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = str(values.get(key) or "").strip()
        if not value:
            raise ValueError(f"missing_template_variable:{key}")
        return value

    rendered = PLACEHOLDER_RE.sub(replace, content).strip()
    if not rendered or len(rendered) > 2000 or CONTROL_RE.search(rendered):
        raise ValueError("rendered_reply_invalid")
    return rendered


def match_comment(comment: dict[str, Any], campaign: dict[str, Any], rules: list[dict[str, Any]]) -> MatchResult:
    text = str(comment.get("text") or comment.get("comment_text") or "")
    author = str(comment.get("author_name") or "")
    fingerprint = str(comment.get("fingerprint") or comment.get("comment_fingerprint") or "")
    if not fingerprint and not text.strip():
        return MatchResult(False, "dedupe_key_missing")
    if _contains_any(author, _json_list(campaign.get("excluded_authors_json"))):
        return MatchResult(False, "author_excluded")
    if _matches_patterns(text, _json_list(campaign.get("excluded_comment_patterns_json"))):
        return MatchResult(False, "comment_pattern_excluded")
    if _contains_any(text, _json_list(campaign.get("negative_keywords_json"))):
        return MatchResult(False, "negative_keyword")

    for rule in sorted([row for row in rules if row.get("enabled", True)], key=lambda row: int(row.get("priority") or 100)):
        rule_result = _match_rule(text, author, rule)
        if rule_result.matched:
            return MatchResult(True, rule_id=str(rule["id"]), template_id=rule.get("reply_template_id"), matched_rule=str(rule.get("name") or rule["id"]))
        if rule_result.blocked_reason:
            return rule_result
    if _contains_any(text, _json_list(campaign.get("positive_keywords_json"))):
        return MatchResult(True, matched_rule="campaign_positive_keywords")
    if _matches_recommendation_context(comment, text):
        return MatchResult(True, matched_rule="recommendation_context")
    return MatchResult(False, "no_rule_match")


def build_candidate_key(tenant_id: str, campaign_id: str, comment: dict[str, Any]) -> str:
    comment_identity = comment.get("comment_id") or comment.get("fingerprint") or comment.get("comment_fingerprint") or comment.get("direct_comment_url") or comment.get("text")
    raw = "|".join([tenant_id, campaign_id, str(comment_identity or "")])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def comments_from_scan_artifacts(artifacts_root: Path, tenant_id: str, execution_id: str) -> list[dict[str, Any]]:
    execution_root = artifacts_root / "tenants" / tenant_id / "executions" / execution_id / "runs"
    comments: list[dict[str, Any]] = []
    if not execution_root.exists():
        return comments
    for path in sorted(execution_root.glob("*/scan_result.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        keyword = payload.get("keyword")
        for item in payload.get("comments") or []:
            if isinstance(item, dict):
                comments.append({**item, "keyword": keyword})
    return comments


def _match_rule(text: str, author: str, rule: dict[str, Any]) -> MatchResult:
    if _contains_any(author, _json_list(rule.get("author_exclude_json"))):
        return MatchResult(False, "author_excluded")
    minimum = rule.get("minimum_length")
    maximum = rule.get("maximum_length")
    if minimum is not None and len(text) < int(minimum):
        return MatchResult(False)
    if maximum is not None and len(text) > int(maximum):
        return MatchResult(False)
    exact = str(rule.get("exact_text") or "").strip()
    if exact and _norm(text) != _norm(exact):
        return MatchResult(False)
    contains_any = _json_list(rule.get("contains_any_json"))
    if contains_any and not _contains_any(text, contains_any):
        return MatchResult(False)
    contains_all = _json_list(rule.get("contains_all_json"))
    if contains_all and not all(_contains(text, item) for item in contains_all):
        return MatchResult(False)
    pattern = str(rule.get("regex_pattern") or "").strip()
    if pattern:
        try:
            if not re.search(pattern, text, re.I):
                return MatchResult(False)
        except re.error as exc:
            raise ValueError("invalid_regex") from exc
    language = str(rule.get("comment_language") or "").strip()
    if language and language != "any" and _detect_language(text) != language:
        return MatchResult(False)
    if not any([exact, contains_any, contains_all, pattern, minimum is not None, maximum is not None, language]):
        return MatchResult(False)
    return MatchResult(True)


def _json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = [value]
    else:
        parsed = value
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _contains(text: str, needle: str) -> bool:
    return _norm(needle) in _norm(text)


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(_contains(text, needle) for needle in needles)


def _matches_recommendation_context(comment: dict[str, Any], text: str) -> bool:
    keyword = str(comment.get("keyword") or "")
    if not _contains_any(keyword, ["recommendation", "recommendations", "recommend", "looking for", "supplier", "vendor"]):
        return False
    value = re.sub(r"\s+", " ", text).strip()
    if not value or len(value) > 90:
        return False
    lowered = value.casefold()
    if any(token in lowered for token in ["赞回复", "查看翻译", "all reactions", "关注"]):
        return False
    has_letter_or_number = bool(re.search(r"[A-Za-z0-9]", value))
    has_business_signal = bool(re.search(r"\b(cafe|food|restaurant|supplier|trading|shop|store|vendor|catering|lechon|trays|pack)\b", lowered))
    return has_letter_or_number and (has_business_signal or len(value.split()) <= 5)


def _matches_patterns(text: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        try:
            if re.search(pattern, text, re.I):
                return True
        except re.error:
            continue
    return False


def _detect_language(text: str) -> str:
    return "zh-CN" if re.search(r"[\u4e00-\u9fff]", text) else "en-US"
