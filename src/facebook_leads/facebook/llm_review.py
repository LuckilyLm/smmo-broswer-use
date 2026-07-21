from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import replace
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .intent_models import IntentMatch, LeadCandidate
from .llm_models import (
    HIGH_RISK_FLAGS,
    LLMLeadReview,
    VALID_INTENT_LEVELS,
    VALID_INTENT_TYPES,
    ReviewedLeadCandidate,
    failed_review,
)


SYSTEM_PROMPT = """你是一个社交媒体销售线索审核助手。

你需要判断用户评论是否表达真实购买或咨询意图。你会收到 Facebook 评论及本地规则命中结果。

任务：
1. 判断是否是真实潜在客户
2. 判断意向等级
3. 判断意向类型
4. 给出简短中文理由
5. 根据评论原语言生成自然、简短、不冒犯的建议回复

判断原则：
- 高意向：明确询问价格、购买方式、配送、门店/地址、要求联系，或说明自己需要产品或服务
- 中等意向：有兴趣但需求不完整，表达可能购买，仍需进一步确认
- 低意向：泛泛询问、信息不完整、意图较弱
- 非线索：纯聊天、玩笑、无关讨论、广告、垃圾信息，或只是提及关键词但没有购买意图

要求：
- 不因为出现单个关键词就强行判定为潜客
- 结合上下文
- 回复建议保持简短
- 不承诺不存在的价格、库存、配送范围、地址或服务能力
- 不编造业务事实
- 信息不足时，建议回复应以询问或引导私聊为主
- 回复使用评论用户主要语言；无法确定语言时使用英文
- 只返回严格 JSON，不要 markdown，不要额外解释

返回格式：
{"results":[{"index":1,"is_lead":true,"confidence":0.95,"intent_level":"high","intent_types":["price"],"reason_zh":"用户明确询问价格。","summary_zh":"询问服务价格。","suggested_reply":"Hi! Thanks for your interest. Please send us a DM and we'll share the details with you.","reply_language":"en","should_reply":true,"risk_flags":[]}]}
"""


class LLMReviewError(ValueError):
    pass


async def review_leads_with_llm(
    leads: list[LeadCandidate],
    *,
    batch_size: int = 10,
    llm_client: Any | None = None,
    model_name: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.1,
    max_retries: int = 2,
    concurrency: int | None = None,
    timeout_seconds: float | None = None,
) -> list[ReviewedLeadCandidate]:
    if not leads:
        return []
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    llm_client = llm_client or build_facebook_leads_llm_client(
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
    )
    detailed = await review_leads_with_llm_detailed(
        leads,
        batch_size=batch_size,
        llm_client=llm_client,
        model_name=model_name,
        temperature=temperature,
        max_retries=max_retries,
        concurrency=concurrency,
        timeout_seconds=timeout_seconds,
    )
    return detailed["reviewed"]


async def review_leads_with_llm_detailed(
    leads: list[LeadCandidate],
    *,
    batch_size: int = 10,
    llm_client: Any | None = None,
    model_name: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.1,
    max_retries: int = 2,
    concurrency: int | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    concurrency = resolve_llm_concurrency(concurrency)
    timeout_seconds = resolve_llm_timeout_seconds(timeout_seconds)
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    if not leads:
        summary = build_llm_review_summary(
            enabled=True,
            model=model_name,
            candidate_count=0,
            batches=[],
            batch_size=batch_size,
            concurrency=concurrency,
            elapsed_ms=0,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
        )
        return {"reviewed": [], "timing": {"llm_review_ms": 0}, "diagnostics": {"batches": [], "summary": summary}, "summary": summary}
    llm_client = llm_client or build_facebook_leads_llm_client(
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
    )
    batch_items = list(enumerate(_chunks(leads, batch_size), start=1))
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(batch_index: int, batch: list[LeadCandidate]) -> dict[str, Any]:
        async with semaphore:
            return await _review_batch(
                batch,
                llm_client=llm_client,
                model_name=model_name or _model_name_from_client(llm_client),
                max_retries=max_retries,
                batch_index=batch_index,
                timeout_seconds=timeout_seconds,
            )

    batch_results = await asyncio.gather(*(run_one(batch_index, batch) for batch_index, batch in batch_items))
    batch_results = sorted(batch_results, key=lambda item: item["diagnostics"]["batch_index"])
    batches = []
    reviewed = []
    prompt_tokens = completion_tokens = total_tokens = 0
    unknown_usage = False
    batch_elapsed_ms_total = 0
    for batch_result in batch_results:
        reviewed.extend(batch_result["reviewed"])
        batches.append(batch_result["diagnostics"])
        batch_elapsed_ms_total += int(batch_result["diagnostics"].get("elapsed_ms") or 0)
        usage = batch_result["diagnostics"].get("usage") or {}
        if usage:
            prompt_tokens += int(usage.get("prompt_tokens") or 0)
            completion_tokens += int(usage.get("completion_tokens") or 0)
            total_tokens += int(usage.get("total_tokens") or 0)
        else:
            unknown_usage = True
    elapsed = int((time.perf_counter() - started) * 1000)
    prompt_value = None if unknown_usage and prompt_tokens == 0 else prompt_tokens
    completion_value = None if unknown_usage and completion_tokens == 0 else completion_tokens
    total_value = None if unknown_usage and total_tokens == 0 else total_tokens
    summary = build_llm_review_summary(
        enabled=True,
        model=model_name or _model_name_from_client(llm_client),
        candidate_count=len(leads),
        batches=batches,
        batch_size=batch_size,
        concurrency=concurrency,
        elapsed_ms=elapsed,
        prompt_tokens=prompt_value,
        completion_tokens=completion_value,
        total_tokens=total_value,
    )
    return {
        "reviewed": reviewed,
        "timing": {
            "llm_review_ms": elapsed,
            "llm_prompt_tokens": prompt_value,
            "llm_completion_tokens": completion_value,
            "llm_total_tokens": total_value,
            "llm_batch_elapsed_ms_total": batch_elapsed_ms_total,
        },
        "diagnostics": {"batches": batches, "llm_call_count": len(batches), "summary": summary},
        "summary": summary,
    }


def resolve_llm_concurrency(value: int | None = None) -> int:
    raw = value if value is not None else os.getenv("FACEBOOK_LEADS_LLM_CONCURRENCY", "2")
    try:
        resolved = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("LLM concurrency must be an integer >= 1") from exc
    if resolved < 1:
        raise ValueError("LLM concurrency must be >= 1")
    return resolved


def resolve_llm_timeout_seconds(value: float | None = None) -> float:
    raw = value if value is not None else os.getenv("FACEBOOK_LEADS_LLM_TIMEOUT_SECONDS", "120")
    try:
        resolved = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("LLM timeout seconds must be a number > 0") from exc
    if resolved <= 0:
        raise ValueError("LLM timeout seconds must be > 0")
    return resolved


def build_facebook_leads_llm_client(
    *,
    provider: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.1,
) -> Any:
    resolved_provider = provider or os.getenv("FACEBOOK_LEADS_LLM_PROVIDER") or os.getenv("DEFAULT_LLM", "openai")
    resolved_model = (
        model_name
        or os.getenv("FACEBOOK_LEADS_LLM_MODEL")
        or _default_model_for_provider(resolved_provider)
    )
    resolved_base_url = base_url or os.getenv("FACEBOOK_LEADS_LLM_BASE_URL") or None
    resolved_api_key = api_key or os.getenv("FACEBOOK_LEADS_LLM_API_KEY") or None
    try:
        from src.utils import llm_provider

        return llm_provider.get_llm_model(
            resolved_provider,
            model_name=resolved_model,
            temperature=temperature,
            base_url=resolved_base_url,
            api_key=resolved_api_key,
        )
    except ModuleNotFoundError:
        return _build_openai_compatible_fallback(
            resolved_provider,
            model_name=resolved_model,
            temperature=temperature,
            base_url=resolved_base_url,
            api_key=resolved_api_key,
        )


def _build_openai_compatible_fallback(
    provider: str,
    *,
    model_name: str,
    temperature: float,
    base_url: str | None,
    api_key: str | None,
) -> Any:
    if provider not in {"openai", "deepseek", "grok", "alibaba", "modelscope", "unbound", "siliconflow"}:
        raise ValueError(f"Cannot build LLM provider '{provider}' because an optional dependency is missing.")
    from langchain_openai import ChatOpenAI

    env_key = {
        "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "grok": "GROK_API_KEY",
        "alibaba": "ALIBABA_API_KEY",
        "modelscope": "MODELSCOPE_API_KEY",
        "unbound": "UNBOUND_API_KEY",
        "siliconflow": "SiliconFLOW_API_KEY",
    }.get(provider, "OPENAI_API_KEY")
    resolved_api_key = api_key or os.getenv(env_key)
    if not resolved_api_key:
        raise ValueError(f"LLM API key not found. Set FACEBOOK_LEADS_LLM_API_KEY or {env_key}.")
    resolved_base_url = base_url or {
        "openai": os.getenv("OPENAI_ENDPOINT", "https://api.openai.com/v1"),
        "deepseek": os.getenv("DEEPSEEK_ENDPOINT", ""),
        "grok": os.getenv("GROK_ENDPOINT", "https://api.x.ai/v1"),
        "alibaba": os.getenv("ALIBABA_ENDPOINT", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        "modelscope": os.getenv("MODELSCOPE_ENDPOINT", ""),
        "unbound": os.getenv("UNBOUND_ENDPOINT", "https://api.getunbound.ai"),
        "siliconflow": os.getenv("SiliconFLOW_ENDPOINT", ""),
    }.get(provider)
    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        base_url=resolved_base_url,
        api_key=resolved_api_key,
    )


async def _review_batch(
    leads: list[LeadCandidate],
    *,
    llm_client: Any,
    model_name: str | None,
    max_retries: int,
    batch_index: int = 1,
    timeout_seconds: float = 120,
) -> dict[str, Any]:
    started = time.perf_counter()
    payload = {"leads": [_lead_payload(index, lead) for index, lead in enumerate(leads, start=1)]}
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
    ]
    attempts = 0
    last_error = ""
    last_error_type = None
    response = None
    timed_out = False
    while attempts <= max_retries:
        attempts += 1
        try:
            response = await asyncio.wait_for(_ainvoke(llm_client, messages), timeout=timeout_seconds)
            content = _message_content(response)
            parsed = parse_llm_review_response(content, leads)
            elapsed = int((time.perf_counter() - started) * 1000)
            return {
                "reviewed": parsed,
                "diagnostics": {
                    "batch_index": batch_index,
                    "candidate_count": len(leads),
                    "batch_size": len(leads),
                    "model": model_name,
                    "elapsed_ms": elapsed,
                    "attempts": attempts,
                    "retry_count": attempts - 1,
                    "usage": extract_usage(response),
                    "status": "success",
                    "item_statuses": [item.llm_review.status for item in parsed],
                },
            }
        except (TimeoutError, asyncio.TimeoutError) as exc:
            timed_out = True
            last_error_type = "timeout"
            last_error = str(exc) or f"batch timed out after {timeout_seconds} seconds"
            break
        except (LLMReviewError, json.JSONDecodeError, ValueError) as exc:
            last_error_type = type(exc).__name__
            last_error = str(exc)
            if attempts > max_retries:
                break
        except Exception as exc:
            last_error_type = type(exc).__name__
            last_error = str(exc)
            break
    elapsed = int((time.perf_counter() - started) * 1000)
    status = "timeout" if timed_out else "failed"
    review_status = "timeout" if timed_out else "failed"
    return {
        "reviewed": [
            _fallback_reviewed_lead(
                lead,
                failed_review(lead.comment_fingerprint, _sanitize_error(last_error), status=review_status),
            )
            for lead in leads
        ],
        "diagnostics": {
            "batch_index": batch_index,
            "candidate_count": len(leads),
            "batch_size": len(leads),
            "model": model_name,
            "elapsed_ms": elapsed,
            "attempts": attempts,
            "retry_count": attempts - 1,
            "usage": extract_usage(response) if response is not None else None,
            "status": status,
            "item_statuses": [review_status for _ in leads],
            "error_type": last_error_type,
            "error_message": _sanitize_error(last_error),
        },
    }


def parse_llm_review_response(content: str, leads: list[LeadCandidate]) -> list[ReviewedLeadCandidate]:
    parsed = json.loads(extract_json_object(content))
    results = parsed.get("results")
    if not isinstance(results, list):
        raise LLMReviewError("results must be a list")
    by_index = {}
    for raw in results:
        if not isinstance(raw, dict):
            continue
        index = raw.get("index")
        if isinstance(index, int):
            by_index[index] = raw
    reviewed = []
    for index, lead in enumerate(leads, start=1):
        raw = by_index.get(index)
        if raw is None:
            reviewed.append(_fallback_reviewed_lead(lead, failed_review(lead.comment_fingerprint, "missing result", status="missing")))
            continue
        try:
            review = validate_llm_review(raw, lead.comment_fingerprint)
        except LLMReviewError as exc:
            review = failed_review(lead.comment_fingerprint, str(exc))
        reviewed.append(_reviewed_lead(lead, review))
    return reviewed


def extract_json_object(content: str) -> str:
    text = (content or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    if start < 0:
        raise LLMReviewError("JSON object not found")
    depth = 0
    in_string = False
    escape = False
    for offset, char in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : offset + 1]
    raise LLMReviewError("JSON object is incomplete")


def validate_llm_review(raw: dict[str, Any], comment_fingerprint: str) -> LLMLeadReview:
    if not isinstance(raw.get("is_lead"), bool):
        raise LLMReviewError("is_lead must be bool")
    confidence = raw.get("confidence")
    if not isinstance(confidence, int | float) or not 0 <= float(confidence) <= 1:
        raise LLMReviewError("confidence must be 0..1")
    intent_level = raw.get("intent_level")
    if intent_level not in VALID_INTENT_LEVELS:
        raise LLMReviewError("invalid intent_level")
    suggested_reply = raw.get("suggested_reply")
    if not isinstance(suggested_reply, str):
        raise LLMReviewError("suggested_reply must be string")
    intent_types = [
        value if value in VALID_INTENT_TYPES else "other"
        for value in raw.get("intent_types", [])
        if isinstance(value, str)
    ] or ["other"]
    risk_flags = [value for value in raw.get("risk_flags", []) if isinstance(value, str)]
    should_reply = bool(raw.get("should_reply"))
    if HIGH_RISK_FLAGS.intersection(risk_flags):
        should_reply = False
    return LLMLeadReview(
        comment_fingerprint=comment_fingerprint,
        status="success",
        is_lead=raw["is_lead"],
        confidence=float(confidence),
        intent_level=intent_level,
        intent_types=intent_types,
        reason_zh=str(raw.get("reason_zh") or ""),
        summary_zh=str(raw.get("summary_zh") or ""),
        suggested_reply=suggested_reply.strip(),
        reply_language=str(raw.get("reply_language") or "en"),
        should_reply=should_reply,
        risk_flags=risk_flags,
    )


def apply_review_to_leads(leads: list[LeadCandidate], reviewed: list[ReviewedLeadCandidate]) -> list[LeadCandidate]:
    by_fingerprint = {item.lead.comment_fingerprint: item for item in reviewed}
    return [_apply_review(lead, by_fingerprint.get(lead.comment_fingerprint)) for lead in leads]


def _apply_review(lead: LeadCandidate, reviewed: ReviewedLeadCandidate | None) -> LeadCandidate:
    if reviewed is None:
        return _apply_rule_defaults(lead)
    return replace(
        lead,
        rule_intent_score=reviewed.rule_intent_score,
        rule_intent_level=reviewed.rule_intent_level,
        rule_matched_keywords=reviewed.rule_matched_keywords,
        rule_matched_categories=reviewed.rule_matched_categories,
        llm_review=reviewed.llm_review.to_dict(),
        llm_review_status=reviewed.llm_review.status,
        final_is_lead=reviewed.final_is_lead,
        final_intent_level=reviewed.final_intent_level,
        final_intent_types=reviewed.final_intent_types,
        final_reason_zh=reviewed.final_reason_zh,
        final_suggested_reply=reviewed.final_suggested_reply,
        decision_source=reviewed.decision_source,
    )


def _apply_rule_defaults(lead: LeadCandidate) -> LeadCandidate:
    return replace(
        lead,
        rule_intent_score=lead.intent_score,
        rule_intent_level=lead.intent_level,
        rule_matched_keywords=_keyword_texts(lead.matched_keywords),
        rule_matched_categories=list(lead.matched_categories),
        llm_review_status="disabled",
        final_is_lead=lead.intent_score > 0,
        final_intent_level=lead.intent_level,
        final_intent_types=[category.lower() for category in lead.matched_categories],
        final_reason_zh=None,
        final_suggested_reply=None,
        decision_source="rule_only",
    )


def _reviewed_lead(lead: LeadCandidate, review: LLMLeadReview) -> ReviewedLeadCandidate:
    if review.status == "success":
        final_is_lead = review.is_lead
        final_level = review.intent_level
        final_types = review.intent_types
        decision_source = "llm"
        reason = review.reason_zh
        reply = review.suggested_reply
    else:
        final_is_lead = lead.intent_score > 0
        final_level = lead.intent_level
        final_types = [category.lower() for category in lead.matched_categories]
        decision_source = "rule_fallback"
        reason = None
        reply = None
    return ReviewedLeadCandidate(
        lead=lead,
        rule_intent_score=lead.intent_score,
        rule_intent_level=lead.intent_level,
        rule_matched_keywords=_keyword_texts(lead.matched_keywords),
        rule_matched_categories=list(lead.matched_categories),
        llm_review=review,
        final_is_lead=final_is_lead,
        final_intent_level=final_level,
        final_intent_types=final_types,
        final_reason_zh=reason,
        final_suggested_reply=reply,
        decision_source=decision_source,
    )


def _fallback_reviewed_lead(lead: LeadCandidate, review: LLMLeadReview) -> ReviewedLeadCandidate:
    return _reviewed_lead(lead, review)


def _lead_payload(index: int, lead: LeadCandidate) -> dict[str, Any]:
    return {
        "index": index,
        "author_name": lead.author_name,
        "comment_text": lead.comment_text,
        "source_content_type": lead.source_content_type,
        "source_content_preview": lead.source_text_preview,
        "source_content_author": lead.source_author_name,
        "rule_intent_score": lead.intent_score,
        "rule_intent_level": lead.intent_level,
        "rule_matched_keywords": _keyword_texts(lead.matched_keywords),
        "rule_matched_categories": list(lead.matched_categories),
    }


def _keyword_texts(matches: list[IntentMatch]) -> list[str]:
    return [match.keyword for match in matches]


async def _ainvoke(llm_client: Any, messages: list[Any]) -> Any:
    if hasattr(llm_client, "ainvoke"):
        return await llm_client.ainvoke(messages)
    if hasattr(llm_client, "invoke"):
        return await asyncio.to_thread(llm_client.invoke, messages)
    raise LLMReviewError("LLM client must expose ainvoke or invoke")


def _message_content(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "\n".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
    return str(content)


def extract_usage(response: Any) -> dict[str, int] | None:
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict):
        return {
            "prompt_tokens": int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }
    metadata = getattr(response, "response_metadata", None)
    if isinstance(metadata, dict):
        token_usage = metadata.get("token_usage") or metadata.get("usage")
        if isinstance(token_usage, dict):
            return {
                "prompt_tokens": int(token_usage.get("prompt_tokens") or 0),
                "completion_tokens": int(token_usage.get("completion_tokens") or 0),
                "total_tokens": int(token_usage.get("total_tokens") or 0),
            }
    return None


def build_llm_review_summary(
    *,
    enabled: bool,
    model: str | None,
    candidate_count: int,
    batches: list[dict[str, Any]],
    batch_size: int | None,
    concurrency: int | None,
    elapsed_ms: int | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
) -> dict[str, Any]:
    if not enabled:
        return {
            "enabled": False,
            "status": "disabled",
            "model": model,
            "candidate_count": candidate_count,
            "reviewed_count": 0,
            "success_count": 0,
            "fallback_count": 0,
            "failed_count": 0,
            "timeout_count": 0,
            "missing_count": 0,
            "call_count": 0,
            "batch_size": batch_size,
            "concurrency": concurrency,
            "elapsed_ms": elapsed_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
    item_statuses = [
        status
        for batch in batches
        for status in (
            batch.get("item_statuses")
            or [batch.get("status") for _ in range(int(batch.get("candidate_count") or batch.get("batch_size") or 0))]
        )
    ]
    success_count = sum(1 for status in item_statuses if status == "success")
    failed_count = sum(1 for status in item_statuses if status == "failed")
    timeout_count = sum(1 for status in item_statuses if status == "timeout")
    missing_count = sum(1 for status in item_statuses if status == "missing")
    fallback_count = max(candidate_count - success_count, 0)
    if candidate_count == 0:
        status = "success"
    elif success_count == candidate_count:
        status = "success"
    elif success_count > 0:
        status = "partial"
    else:
        status = "failed"
    return {
        "enabled": True,
        "status": status,
        "model": model,
        "candidate_count": candidate_count,
        "reviewed_count": success_count,
        "success_count": success_count,
        "fallback_count": fallback_count,
        "failed_count": failed_count,
        "timeout_count": timeout_count,
        "missing_count": missing_count,
        "call_count": len(batches),
        "batch_size": batch_size,
        "concurrency": concurrency,
        "elapsed_ms": elapsed_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _sanitize_error(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"sk-[A-Za-z0-9_-]+", "sk-***", text)
    text = re.sub(r"Bearer\s+[A-Za-z0-9._-]+", "Bearer ***", text, flags=re.I)
    return text[:500]


def _chunks(items: list[LeadCandidate], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _default_model_for_provider(provider: str) -> str:
    from src.utils import config as llm_config

    names = llm_config.model_names.get(provider)
    if names:
        return names[0]
    return "gpt-4o"


def _model_name_from_client(llm_client: Any) -> str | None:
    return (
        getattr(llm_client, "model_name", None)
        or getattr(llm_client, "model", None)
        or getattr(llm_client, "model_id", None)
    )
