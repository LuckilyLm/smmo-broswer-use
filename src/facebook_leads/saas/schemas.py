from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .reply_automation import ALLOWED_TEMPLATE_VARIABLES, PLACEHOLDER_RE


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(StrictRequest):
    email: str
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("invalid email")
        return normalized


class ChangePasswordRequest(StrictRequest):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


class CreatePlatformAccountRequest(StrictRequest):
    platform: str
    display_name: str = Field(min_length=1, max_length=255)
    external_account_id: str | None = Field(default=None, max_length=255)
    external_account_name: str | None = Field(default=None, max_length=255)


class UpdatePlatformAccountRequest(StrictRequest):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    external_account_id: str | None = Field(default=None, max_length=255)
    external_account_name: str | None = Field(default=None, max_length=255)


class ResetProfileRequest(StrictRequest):
    confirm: str


class CampaignRequest(StrictRequest):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    platform_account_id: str | None = None
    status: str | None = None
    target_policy: str | None = None
    max_contents: int | None = Field(default=None, ge=1, le=100)
    max_comments: int | None = Field(default=None, ge=1, le=1000)
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    max_leads: int | None = Field(default=None, ge=1)
    daily_limit: int | None = Field(default=None, ge=1)
    llm_enabled: bool | None = None
    lead_detection_mode: str | None = Field(default=None, pattern=r"^(rules_only|rules_with_llm)$")
    reply_mode: str | None = Field(default=None, pattern=r"^(disabled|manual_approval|automatic)$")
    default_reply_template_id: str | None = None
    positive_keywords_json: list[str] | None = None
    negative_keywords_json: list[str] | None = None
    excluded_authors_json: list[str] | None = None
    excluded_comment_patterns_json: list[str] | None = None
    default_whatsapp: str | None = Field(default=None, max_length=255)
    default_email: str | None = Field(default=None, max_length=255)
    default_website: str | None = Field(default=None, max_length=500)
    default_contact_text: str | None = None
    reply_daily_limit: int | None = Field(default=None, ge=1)
    reply_per_minute_limit: int | None = Field(default=None, ge=1)
    reply_per_hour_limit: int | None = Field(default=None, ge=1)
    reply_min_interval_seconds: int | None = Field(default=None, ge=1)
    target_regions_json: list[str] | None = Field(default=None, max_length=50)
    content_types_json: list[str] | None = Field(default=None, max_length=20)
    content_language: str | None = Field(default=None, min_length=2, max_length=20)


class CreateCampaignRequest(StrictRequest):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    platform_account_id: str
    status: str | None = None
    target_policy: str | None = None
    max_contents: int | None = Field(default=None, ge=1, le=100)
    max_comments: int | None = Field(default=None, ge=1, le=1000)
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    max_leads: int | None = Field(default=None, ge=1)
    daily_limit: int | None = Field(default=None, ge=1)
    llm_enabled: bool | None = None
    lead_detection_mode: str | None = Field(default=None, pattern=r"^(rules_only|rules_with_llm)$")
    reply_mode: str | None = Field(default=None, pattern=r"^(disabled|manual_approval|automatic)$")
    default_reply_template_id: str | None = None
    positive_keywords_json: list[str] | None = None
    negative_keywords_json: list[str] | None = None
    excluded_authors_json: list[str] | None = None
    excluded_comment_patterns_json: list[str] | None = None
    default_whatsapp: str | None = Field(default=None, max_length=255)
    default_email: str | None = Field(default=None, max_length=255)
    default_website: str | None = Field(default=None, max_length=500)
    default_contact_text: str | None = None
    reply_daily_limit: int | None = Field(default=None, ge=1)
    reply_per_minute_limit: int | None = Field(default=None, ge=1)
    reply_per_hour_limit: int | None = Field(default=None, ge=1)
    reply_min_interval_seconds: int | None = Field(default=None, ge=1)
    target_regions_json: list[str] | None = Field(default=None, max_length=50)
    content_types_json: list[str] | None = Field(default=None, max_length=20)
    content_language: str | None = Field(default=None, min_length=2, max_length=20)
    initial_keywords: list[str] | None = Field(default=None, max_length=50)


class UpdateCampaignRequest(CampaignRequest):
    pass


class ScheduleRequest(StrictRequest):
    enabled: bool = False
    schedule_type: str
    interval_minutes: int | None = Field(default=None, ge=1)
    daily_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


class CreateKeywordRequest(StrictRequest):
    keyword: str = Field(min_length=1, max_length=255)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=10_000)


class UpdateKeywordRequest(StrictRequest):
    keyword: str | None = Field(default=None, min_length=1, max_length=255)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=10_000)


class BulkCreateKeywordsRequest(StrictRequest):
    keywords: list[str] = Field(min_length=1, max_length=50)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=10_000)


def _validate_template_content(value: str) -> str:
    content = value.strip()
    unknown = set(PLACEHOLDER_RE.findall(content)) - ALLOWED_TEMPLATE_VARIABLES
    if unknown:
        raise ValueError(f"unknown_template_variable:{sorted(unknown)[0]}")
    return content


class CreateReplyTemplateRequest(StrictRequest):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    content: str = Field(min_length=1, max_length=2000)
    platform: str = Field(default="facebook", pattern=r"^facebook$")
    language: str = Field(default="zh-CN", pattern=r"^(zh-CN|en-US)$")
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=10_000)
    is_default: bool | None = None

    @field_validator("content")
    @classmethod
    def valid_content(cls, value: str) -> str:
        return _validate_template_content(value)


class UpdateReplyTemplateRequest(StrictRequest):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    content: str | None = Field(default=None, min_length=1, max_length=2000)
    platform: str | None = Field(default=None, pattern=r"^facebook$")
    language: str | None = Field(default=None, pattern=r"^(zh-CN|en-US)$")
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=10_000)
    is_default: bool | None = None

    @field_validator("content")
    @classmethod
    def valid_content(cls, value: str | None) -> str | None:
        return _validate_template_content(value) if value is not None else value


class PreviewReplyTemplateRequest(StrictRequest):
    template_id: str | None = None
    campaign_id: str | None = None
    content: str | None = Field(default=None, min_length=1, max_length=2000)
    comment: dict[str, Any] | None = None

    @field_validator("content")
    @classmethod
    def valid_content(cls, value: str | None) -> str | None:
        return _validate_template_content(value) if value is not None else value


def _validate_regex_pattern(value: str | None) -> str | None:
    if value is None:
        return value
    pattern = value.strip()
    if not pattern:
        return None
    if len(pattern) > 500:
        raise ValueError("regex_too_long")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError("invalid_regex") from exc
    return pattern


class ReplyMatchRuleFields(StrictRequest):
    campaign_id: str | None = None
    reply_template_id: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=10_000)
    contains_any_json: list[str] | None = Field(default=None, max_length=50)
    contains_all_json: list[str] | None = Field(default=None, max_length=50)
    exact_text: str | None = Field(default=None, max_length=500)
    regex_pattern: str | None = Field(default=None, max_length=500)
    author_exclude_json: list[str] | None = Field(default=None, max_length=50)
    comment_language: str | None = Field(default=None, pattern=r"^(any|zh-CN|en-US)$")
    minimum_length: int | None = Field(default=None, ge=1, le=5000)
    maximum_length: int | None = Field(default=None, ge=1, le=5000)

    @field_validator("regex_pattern")
    @classmethod
    def valid_regex(cls, value: str | None) -> str | None:
        return _validate_regex_pattern(value)


class CreateReplyMatchRuleRequest(ReplyMatchRuleFields):
    campaign_id: str
    name: str = Field(min_length=1, max_length=255)


class UpdateReplyMatchRuleRequest(ReplyMatchRuleFields):
    pass


class TestReplyMatchRuleRequest(ReplyMatchRuleFields):
    comment_text: str = Field(min_length=1, max_length=5000)
    author_name: str | None = Field(default=None, max_length=255)


class RejectReplyCandidateRequest(StrictRequest):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("reject_reason_required")
        return reason


class UpdateReplyCandidateContentRequest(StrictRequest):
    rendered_reply_text: str = Field(min_length=1, max_length=2000)

    @field_validator("rendered_reply_text")
    @classmethod
    def valid_rendered_reply_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("rendered_reply_invalid")
        return text


class BulkApproveReplyCandidatesRequest(StrictRequest):
    candidate_ids: list[str] = Field(min_length=1, max_length=100)


class BulkRejectReplyCandidatesRequest(BulkApproveReplyCandidatesRequest):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("reject_reason_required")
        return reason


class UpdateLeadRequest(StrictRequest):
    status: str | None = Field(default=None, pattern=r"^(new|open|assigned|contacted|qualified|invalid|archived)$")
    manual_intent_level: str | None = Field(default=None, pattern=r"^(low|medium|high|unknown)$")
    assigned_user_id: str | None = None
    contacted_at: datetime | None = None
    invalid_reason: str | None = Field(default=None, max_length=1000)


class CreateLeadNoteRequest(StrictRequest):
    note: str = Field(min_length=1, max_length=5000)
    metadata_json: dict[str, Any] | None = None

    @field_validator("note")
    @classmethod
    def valid_note(cls, value: str) -> str:
        note = value.strip()
        if not note:
            raise ValueError("note_required")
        return note


class AssignLeadRequest(StrictRequest):
    assigned_user_id: str


class MarkLeadInvalidRequest(StrictRequest):
    invalid_reason: str = Field(min_length=1, max_length=1000)

    @field_validator("invalid_reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("invalid_reason_required")
        return reason


class BulkUpdateLeadsRequest(StrictRequest):
    lead_ids: list[str] = Field(min_length=1, max_length=100)
    status: str | None = Field(default=None, pattern=r"^(new|open|assigned|contacted|qualified|invalid|archived)$")
    manual_intent_level: str | None = Field(default=None, pattern=r"^(low|medium|high|unknown)$")
    assigned_user_id: str | None = None


class GenericPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    def payload(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class InviteMemberRequest(StrictRequest):
    email: str
    role: str = Field(pattern=r"^(admin|member|viewer)$")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("invalid email")
        return normalized


class AcceptInvitationRequest(StrictRequest):
    email: str | None = None
    password: str | None = Field(default=None, min_length=8)
    display_name: str | None = Field(default=None, min_length=1, max_length=255)


class UpdateMemberRoleRequest(StrictRequest):
    role: str = Field(pattern=r"^(owner|admin|member|viewer)$")


class TransferOwnershipRequest(StrictRequest):
    target_user_id: str


class UpdateTenantSettingsRequest(StrictRequest):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    timezone: str | None = None
    default_target_policy: str | None = Field(default=None, pattern=r"^(owned_only|allowlist|discovery_only)$")
    default_min_confidence: float | None = Field(default=None, ge=0, le=1)
    default_daily_limit: int | None = Field(default=None, ge=1, le=10_000)
    default_whatsapp: str | None = Field(default=None, max_length=255)
    default_email: str | None = Field(default=None, max_length=255)
    default_website: str | None = Field(default=None, max_length=500)
    default_contact_text: str | None = None
    tenant_reply_enabled: bool | None = None

    @field_validator("timezone")
    @classmethod
    def valid_optional_timezone(cls, value: str | None) -> str | None:
        if value:
            ZoneInfo(value)
        return value


class PlanRequest(StrictRequest):
    code: str | None = Field(default=None, min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, pattern=r"^(active|inactive)$")
    max_users: int | None = Field(default=None, ge=1)
    max_platform_accounts: int | None = Field(default=None, ge=1)
    max_campaigns: int | None = Field(default=None, ge=1)
    max_monthly_executions: int | None = Field(default=None, ge=1)
    max_monthly_tokens: int | None = Field(default=None, ge=1)
    max_monthly_leads: int | None = Field(default=None, ge=1)
    allow_scheduler: bool | None = None
    allow_multi_keyword: bool | None = None
    allow_advanced_reports: bool | None = None


class CreatePlanRequest(StrictRequest):
    code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    status: str | None = Field(default=None, pattern=r"^(active|inactive)$")
    max_users: int | None = Field(default=None, ge=1)
    max_platform_accounts: int | None = Field(default=None, ge=1)
    max_campaigns: int | None = Field(default=None, ge=1)
    max_monthly_executions: int | None = Field(default=None, ge=1)
    max_monthly_tokens: int | None = Field(default=None, ge=1)
    max_monthly_leads: int | None = Field(default=None, ge=1)
    allow_scheduler: bool | None = None
    allow_multi_keyword: bool | None = None
    allow_advanced_reports: bool | None = None


class UpdatePlanRequest(PlanRequest):
    pass


class UpdateSubscriptionRequest(StrictRequest):
    plan_id: str | None = None
    plan_code: str | None = None
    status: str | None = Field(default=None, pattern=r"^(trial|active|past_due|suspended|cancelled)$")
    tenant_status: str | None = Field(default=None, pattern=r"^(active|suspended)$")
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    overrides_json: dict[str, int | None] | None = None
