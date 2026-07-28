# SaaS Backend API Contract

Date: 2026-07-27

Scope: current FastAPI backend contract for `web/saas-dashboard` integration. This document is generated from the current backend route and schema code. It is intended for frontend adaptation work.

## Global Rules

- Base path: all business endpoints are under `/api`.
- Auth: server session cookie `leadflow_session`; bearer token is still accepted by backend tests and legacy callers, but the SaaS frontend should use the session cookie flow.
- JSON: request and response bodies use `application/json` unless the route returns `204 No Content`.
- Tenant/workspace: most endpoints are tenant-scoped by the current session context. Workspace switching uses `POST /api/tenants/{tenant_id}/switch`.
- Strict request bodies: new CRUD endpoints should reject unknown fields with `422`. Existing legacy endpoints that still accept loose objects are called out below.
- Deletes are usually soft archive/disable at service level; do not assume physical deletion from UI.
- Reply sending remains guarded by backend `SAAS_SYSTEM_SEND_ENABLED`; frontend must treat `system_send_disabled` as a blocking state.

## Error Format

All frontend requests should handle this common shape:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "Request validation failed",
    "fields": [
      { "field": "reason", "message": "Field required" }
    ]
  }
}
```

Important statuses:

| HTTP | Meaning | Frontend handling |
| --- | --- | --- |
| 401 | Session expired or invalid | Clear auth state, show one warning, redirect to login. |
| 403 | Permission denied, tenant suspended, feature unavailable | Disable/hide action when possible; show clear permission message. |
| 404 | Tenant-scoped resource not found | Treat as missing or inaccessible. |
| 409 | State conflict | Keep modal open; show conflict reason such as `candidate_not_rejectable`. |
| 422 | Request validation error | Map `error.fields[*].field` to form fields. |
| 429 | Quota/rate limit | Show quota message; disable quota-bound operation. |
| 500 | Server error | Show retryable error state. |

## Common Paging Shape

List endpoints that support paging return:

```ts
type Page<T> = {
  items: T[];
  limit: number;
  offset: number;
  total: number;
};
```

Some legacy list endpoints still return a plain array; see endpoint tables.

## Auth And Workspace

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| `POST` | `/api/auth/login` | `LoginRequest` | Session/user payload and `leadflow_session` cookie. |
| `POST` | `/api/auth/logout` | none | `204`/empty response; cookie cleared. |
| `GET` | `/api/auth/me` | none | Current user, tenant, role, membership. |
| `GET` | `/api/auth/session` | none | Same as `/api/auth/me`; allowed while password change is required. |
| `GET` | `/api/auth/sessions` | none | Current user's active session page. |
| `DELETE` | `/api/auth/sessions/{session_id}` | none | `204`; revokes one owned session. |
| `POST` | `/api/auth/sessions/revoke-others` | none | `{ revoked }`. |
| `POST` | `/api/auth/change-password` | `ChangePasswordRequest` | Success payload; old sessions revoked. |
| `GET` | `/api/tenants` | none | `Tenant[]`. |
| `POST` | `/api/tenants/{tenant_id}/switch` | none | New current session context. |

```ts
type LoginRequest = {
  email: string;
  password: string;
};

type ChangePasswordRequest = {
  current_password: string;
  new_password: string; // min 8
};
```

## Dashboard And System

| Method | Path | Response |
| --- | --- | --- |
| `GET` | `/api/dashboard/summary` | Dashboard summary cards/lists. |
| `GET` | `/api/system/runtime-capabilities` | Browser runtime availability. |
| `GET` | `/api/system/dependencies` | Dependency status. |
| `GET` | `/api/system/worker-status` | Worker heartbeat. |
| `GET` | `/api/system/scheduler-status` | Scheduler heartbeat. |
| `GET` | `/api/settings` | Tenant settings plus `system_send_enabled`, reply safety message. |
| `PATCH` | `/api/settings` | `UpdateTenantSettingsRequest`. |
| `GET` | `/api/usage/summary` | Current plan, subscription, limits, remaining usage. |

## Platform Accounts

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| `GET` | `/api/platform-accounts` | query none | `PlatformAccount[]`. |
| `POST` | `/api/platform-accounts` | `CreatePlatformAccountRequest` | `PlatformAccount`. |
| `GET` | `/api/platform-accounts/{account_id}` | none | Platform account aggregate detail. |
| `PATCH` | `/api/platform-accounts/{account_id}` | `UpdatePlatformAccountRequest` | `PlatformAccount`. |
| `DELETE` | `/api/platform-accounts/{account_id}` | none | `204`. |
| `POST` | `/api/platform-accounts/{account_id}/connect` | none | Runtime/connect payload. |
| `POST` | `/api/platform-accounts/{account_id}/check-login` | none | Login check payload. |
| `POST` | `/api/platform-accounts/{account_id}/reconnect` | none | Runtime/connect payload. |
| `POST` | `/api/platform-accounts/{account_id}/stop-runtime` | none | Runtime payload. |
| `POST` | `/api/platform-accounts/{account_id}/restart-runtime` | none | Runtime payload. |
| `POST` | `/api/platform-accounts/{account_id}/reset-profile` | `ResetProfileRequest` | Runtime payload. |
| `GET` | `/api/platform-accounts/{account_id}/runtime` | none | `BrowserRuntime` or runtime detail. |

```ts
type CreatePlatformAccountRequest = {
  platform: string;
  display_name: string;
  external_account_id?: string | null;
  external_account_name?: string | null;
};

type UpdatePlatformAccountRequest = {
  display_name?: string;
  external_account_id?: string | null;
  external_account_name?: string | null;
};

type ResetProfileRequest = {
  confirm: string;
};

type PlatformAccount = {
  id: string;
  tenant_id: string;
  platform: string;
  display_name: string;
  external_account_id?: string | null;
  external_account_name?: string | null;
  connection_status: string;
  browser_runtime_id?: string | null;
  login_status: string;
  last_login_check_at?: string | null;
  last_connection_error?: string | null;
  connection_metadata?: unknown;
  created_at: string;
  updated_at: string;
  runtime?: BrowserRuntime | null;
};
```

## Campaigns And Keywords

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| `GET` | `/api/campaigns?limit=&offset=` | none | `Page<Campaign>`. Without query params legacy callers may receive array behavior in older code paths; frontend should pass paging params. |
| `GET` | `/api/campaigns/{campaign_id}` | none | Campaign aggregate detail. |
| `POST` | `/api/campaigns` | `CreateCampaignRequest` | `Campaign`; creates campaign and `initial_keywords` transactionally. |
| `PATCH` | `/api/campaigns/{campaign_id}` | `UpdateCampaignRequest` | `Campaign`. |
| `DELETE` | `/api/campaigns/{campaign_id}` | none | `204`; soft delete/archive behavior. |
| `POST` | `/api/campaigns/{campaign_id}/run` | none | Queued execution payload; `send_disabled` remains `true`. |
| `GET` | `/api/campaigns/{campaign_id}/schedule` | none | Schedule or empty/default payload. |
| `PUT` | `/api/campaigns/{campaign_id}/schedule` | `ScheduleRequest` | Schedule. |
| `POST` | `/api/campaigns/{campaign_id}/schedule/disable` | none | Disabled schedule. |
| `GET` | `/api/campaigns/{campaign_id}/keywords` | none | `CampaignKeyword[]`. |
| `POST` | `/api/campaigns/{campaign_id}/keywords` | `CreateKeywordRequest` | `CampaignKeyword`. |
| `POST` | `/api/campaigns/{campaign_id}/keywords/bulk` | `BulkCreateKeywordsRequest` | `{ items, created }`; transactional. |
| `PATCH` | `/api/keywords/{keyword_id}` | `UpdateKeywordRequest` | `CampaignKeyword`. |
| `DELETE` | `/api/keywords/{keyword_id}` | none | `204`. |

```ts
type CreateCampaignRequest = {
  name: string;
  description?: string | null;
  platform_account_id: string;
  status?: string | null;
  target_policy?: string | null;
  max_contents?: number | null; // 1..100
  max_comments?: number | null; // 1..1000
  min_confidence?: number | null; // 0..1
  max_leads?: number | null;
  daily_limit?: number | null;
  llm_enabled?: boolean | null;
  lead_detection_mode?: "rules_only" | "rules_with_llm" | null;
  reply_mode?: "disabled" | "manual_approval" | "automatic" | null;
  default_reply_template_id?: string | null;
  positive_keywords_json?: string[] | null;
  negative_keywords_json?: string[] | null;
  excluded_authors_json?: string[] | null;
  excluded_comment_patterns_json?: string[] | null;
  default_whatsapp?: string | null;
  default_email?: string | null;
  default_website?: string | null;
  default_contact_text?: string | null;
  reply_daily_limit?: number | null;
  reply_per_minute_limit?: number | null;
  reply_per_hour_limit?: number | null;
  reply_min_interval_seconds?: number | null;
  target_regions_json?: string[] | null;
  content_types_json?: string[] | null;
  content_language?: string | null;
  initial_keywords?: string[] | null; // max 50
};

type UpdateCampaignRequest = Partial<Omit<CreateCampaignRequest, "initial_keywords">>;

type ScheduleRequest = {
  enabled: boolean;
  schedule_type: string;
  interval_minutes?: number | null;
  daily_time?: string | null; // HH:MM
  timezone: string;
};

type CreateKeywordRequest = {
  keyword: string;
  enabled?: boolean | null;
  priority?: number | null;
};

type UpdateKeywordRequest = Partial<CreateKeywordRequest>;

type BulkCreateKeywordsRequest = {
  keywords: string[]; // 1..50, max item length enforced by service
  enabled?: boolean | null;
  priority?: number | null;
};
```

## Leads

| Method | Path | Query | Response |
| --- | --- | --- | --- |
| `GET` | `/api/leads` | `campaign_id`, `platform`, `status`, `intent_level`, `manual_intent_level`, `assigned_user_id`, `rule_intent_level`, `final_intent_level`, `reply_allowed`, `keyword`, `created_from`, `created_to`, `search`, `limit`, `offset` | `Page<Lead>`. |
| `GET` | `/api/leads/{lead_id}` | none | Lead detail with campaign/account. |
| `PATCH` | `/api/leads/{lead_id}` | `UpdateLeadRequest` | `Lead`. |
| `GET` | `/api/leads/{lead_id}/notes` | `limit`, `offset` | `Page<LeadNote>`. |
| `POST` | `/api/leads/{lead_id}/notes` | `CreateLeadNoteRequest` | `LeadNote`. |
| `POST` | `/api/leads/{lead_id}/assign` | `AssignLeadRequest` | `Lead`. |
| `POST` | `/api/leads/{lead_id}/mark-contacted` | none | `Lead`. |
| `POST` | `/api/leads/{lead_id}/mark-invalid` | `MarkLeadInvalidRequest` | `Lead`. |
| `POST` | `/api/leads/bulk-update` | `BulkUpdateLeadsRequest` | `{ items, updated }`. |
| `GET` | `/api/leads/{lead_id}/timeline` | none | `Page<TimelineItem>`. |

```ts
type UpdateLeadRequest = {
  status?: "new" | "open" | "assigned" | "contacted" | "qualified" | "invalid" | "archived";
  manual_intent_level?: "low" | "medium" | "high" | "unknown";
  assigned_user_id?: string | null;
  contacted_at?: string | null;
  invalid_reason?: string | null;
};

type CreateLeadNoteRequest = {
  note: string;
  metadata_json?: Record<string, unknown> | null;
};

type AssignLeadRequest = {
  assigned_user_id: string;
};

type MarkLeadInvalidRequest = {
  invalid_reason: string;
};

type BulkUpdateLeadsRequest = {
  lead_ids: string[]; // 1..100
  status?: UpdateLeadRequest["status"];
  manual_intent_level?: UpdateLeadRequest["manual_intent_level"];
  assigned_user_id?: string | null;
};
```

Lead state guards:

- Repeated transition to the same state is idempotent.
- Invalid state transitions return `409 invalid_lead_status_transition`.
- `invalid` requires `invalid_reason`.
- Assignment requires an active user in the current tenant.
- All write operations require tenant writeability, write permission, tenant-scoped lead ownership, and audit logging.

## Reply Templates

Template variable whitelist:

```text
{{whatsapp}}
{{email}}
{{website}}
{{contact}}
{{campaign_name}}
{{keyword}}
{{author_name}}
```

Unknown variables are rejected by API schema and service rendering.

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| `GET` | `/api/reply-templates` | none | `ReplyTemplate[]` active templates only. |
| `POST` | `/api/reply-templates` | `CreateReplyTemplateRequest` | `ReplyTemplate`. |
| `PATCH` | `/api/reply-templates/{template_id}` | `UpdateReplyTemplateRequest` | `ReplyTemplate`. |
| `POST` | `/api/reply-templates/{template_id}/copy` | none | Copied `ReplyTemplate`; `is_default=false`. |
| `DELETE` | `/api/reply-templates/{template_id}` | none | `204`; archives and disables. Blocks default or in-use templates with `409`. |
| `POST` | `/api/reply-templates/preview` | `PreviewReplyTemplateRequest` | `{ rendered, system_send_enabled }`. |

```ts
type CreateReplyTemplateRequest = {
  name: string;
  description?: string | null;
  content: string; // 1..2000
  platform?: "facebook";
  language?: "zh-CN" | "en-US";
  enabled?: boolean | null;
  priority?: number | null; // 1..10000
  is_default?: boolean | null;
};

type UpdateReplyTemplateRequest = Partial<CreateReplyTemplateRequest>;

type PreviewReplyTemplateRequest = {
  template_id?: string | null;
  campaign_id?: string | null;
  content?: string | null;
  comment?: Record<string, unknown> | null;
};
```

## Reply Matching Rules

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| `GET` | `/api/reply-match-rules?campaign_id=` | none | `ReplyMatchRule[]`. |
| `POST` | `/api/reply-match-rules` | `CreateReplyMatchRuleRequest` | `ReplyMatchRule`. |
| `PATCH` | `/api/reply-match-rules/{rule_id}` | `UpdateReplyMatchRuleRequest` | `ReplyMatchRule`. |
| `POST` | `/api/reply-match-rules/{rule_id}/copy` | none | Copied `ReplyMatchRule`; `enabled=false`. |
| `DELETE` | `/api/reply-match-rules/{rule_id}` | none | `204`; archives and disables. |
| `POST` | `/api/reply-match-rules/test` | `TestReplyMatchRuleRequest` | Match test result. |

Regex rules:

- `regex_pattern` max length is 500.
- Invalid regex returns `422` at API level or `400 invalid_regex` from service-level validation paths.
- `minimum_length` and `maximum_length` must be `1..5000`; service rejects `minimum_length > maximum_length`.

```ts
type ReplyMatchRuleFields = {
  campaign_id?: string | null;
  reply_template_id?: string | null;
  name?: string | null;
  enabled?: boolean | null;
  priority?: number | null; // 1..10000
  contains_any_json?: string[] | null;
  contains_all_json?: string[] | null;
  exact_text?: string | null;
  regex_pattern?: string | null;
  author_exclude_json?: string[] | null;
  comment_language?: "any" | "zh-CN" | "en-US" | null;
  minimum_length?: number | null;
  maximum_length?: number | null;
};

type CreateReplyMatchRuleRequest = ReplyMatchRuleFields & {
  campaign_id: string;
  name: string;
};

type UpdateReplyMatchRuleRequest = ReplyMatchRuleFields;

type TestReplyMatchRuleRequest = ReplyMatchRuleFields & {
  comment_text: string;
  author_name?: string | null;
};

type ReplyMatchRuleTestResult = {
  matched: boolean;
  blocked_reason?: string | null;
  rule_id?: string | null;
  template_id?: string | null;
  matched_rule?: string | null;
  status: "matched" | "blocked" | "not_matched";
  selected_template_id?: string | null;
  selected_template_name?: string | null;
};
```

## Reply Tasks: Candidates And Plans

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| `GET` | `/api/reply-candidates` | query `campaign_id`, `execution_id`, `reply_plan_id`, `status`, `limit`, `offset` | `Page<ReplyCandidate>`. |
| `POST` | `/api/reply-candidates/{candidate_id}/approve` | none | `ReplyCandidate`. |
| `POST` | `/api/reply-candidates/{candidate_id}/reject` | `RejectReplyCandidateRequest` | `ReplyCandidate`. |
| `POST` | `/api/reply-candidates/{candidate_id}/cancel` | none | `ReplyCandidate`. |
| `POST` | `/api/reply-candidates/bulk-approve` | `BulkApproveReplyCandidatesRequest` | `{ items, updated }`. |
| `POST` | `/api/reply-candidates/bulk-reject` | `BulkRejectReplyCandidatesRequest` | `{ items, updated }`. |
| `PATCH` | `/api/reply-candidates/{candidate_id}/content` | `UpdateReplyCandidateContentRequest` | `ReplyCandidate`. |
| `GET` | `/api/reply-plans` | query `campaign_id`, `execution_id`, `status`, `limit`, `offset` | `Page<ReplyPlan>`. |
| `POST` | `/api/reply-plans/{plan_id}/approve` | none | `ReplyPlan`. |
| `POST` | `/api/reply-plans/{plan_id}/cancel` | none | `ReplyPlan`. |
| `POST` | `/api/reply-plans/{plan_id}/execute` | none | `ReplyPlan`; blocked with record when system send is off. |

```ts
type RejectReplyCandidateRequest = {
  reason: string; // required, non-empty, max 500
};

type UpdateReplyCandidateContentRequest = {
  rendered_reply_text: string; // required, non-empty, max 2000
};

type BulkApproveReplyCandidatesRequest = {
  candidate_ids: string[]; // 1..100
};

type BulkRejectReplyCandidatesRequest = {
  candidate_ids: string[]; // 1..100
  reason: string; // required
};
```

Candidate state guards:

- Approve allowed from `pending_approval` or `blocked`; repeat approve on `approved`/`sent` is idempotent.
- Reject requires explicit reason and is allowed from `pending_approval`, `blocked`, `approved`.
- Cancel allowed from `pending_approval`, `blocked`, `approved`.
- Content edit is rejected for `sent`, `rejected`, `cancelled` with `409 candidate_content_locked`.

Plan state guards:

- Approve allowed from `pending_approval` or `approved`; executed plans are idempotent.
- Cancel allowed from `pending_approval`, `approved`, `blocked`.
- Execute still checks backend send guard. If `SAAS_SYSTEM_SEND_ENABLED=false`, backend sets plan `blocked`, inserts a `reply_records` row with `error_type=system_send_disabled`, and does not send.

## Reply Records

| Method | Path | Query | Response |
| --- | --- | --- | --- |
| `GET` | `/api/reply-records` | `campaign_id`, `platform_account_id`, `status`, `verified`, `error_type`, `author_name`, `keyword`, `created_from`, `created_to`, `limit`, `offset` | `Page<ReplyRecord>`. |
| `GET` | `/api/reply-records/{record_id}` | none | Reply record aggregate detail. |

Reply records are audit records. There is no delete API.

## Executions

| Method | Path | Query/Request | Response |
| --- | --- | --- | --- |
| `GET` | `/api/executions` | `limit`, `offset` | `Page<Execution>` when paging params are present; legacy array otherwise. |
| `GET` | `/api/executions/{execution_id}` | none | `Execution`. |
| `GET` | `/api/executions/{execution_id}/keywords` | none | `ExecutionKeyword[]`. |
| `POST` | `/api/executions/{execution_id}/cancel` | none | Updated/cancel-requested execution. |
| `POST` | `/api/executions/{execution_id}/retry` | none | Queued retry payload. |
| `GET` | `/api/executions/{execution_id}/timeline` | none | `Page<TimelineItem>`. |
| `GET` | `/api/executions/{execution_id}/artifacts` | none | `Page<Artifact>`. |
| `GET` | `/api/executions/{execution_id}/logs` | `limit`, `offset` | Sanitized log page. |
| `GET` | `/api/executions/{execution_id}/screenshots` | none | Screenshot artifact page. |
| `GET` | `/api/executions/{execution_id}/token-usage` | `limit`, `offset` | `Page<TokenUsage>`. |

Execution records always include `send_disabled`; frontend should display it and keep reply execution UI disabled when true.

Retry state guards:

- Allowed for `failed`, `cancelled`, or retryable error classifications.
- Rejected with `409 execution_not_retryable` for `queued`, `running`, and `completed`.
- Retry enqueues a new execution and preserves historical evidence.
- Artifact and log access is tenant/execution scoped; logs redact cookies, bearer tokens, access tokens, CSRF headers, and password-like fields.

## Token Usage

| Method | Path | Query | Response |
| --- | --- | --- | --- |
| `GET` | `/api/token-usage/summary` | backend-defined range/grouping query | Summary payload. |
| `GET` | `/api/token-usage/details` | backend-defined filters | Detail list/page payload. |

## Members And Invitations

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| `GET` | `/api/tenant/members` | none | `TenantMember[]`. |
| `GET` | `/api/tenant/members/{membership_id}` | none | Member aggregate detail. |
| `POST` | `/api/tenant/members` | `InviteMemberRequest` | Invitation/member payload. |
| `PATCH` | `/api/tenant/members/{membership_id}` | `UpdateMemberRoleRequest` | Updated member. |
| `DELETE` | `/api/tenant/members/{membership_id}` | none | `204`. |
| `POST` | `/api/tenant/transfer-ownership` | `TransferOwnershipRequest` | Updated ownership payload. |
| `POST` | `/api/tenant/invitations` | `InviteMemberRequest` | Invitation payload. |
| `GET` | `/api/tenant/invitations` | none | `Invitation[]`. |
| `GET` | `/api/tenant/invitations/{invitation_id}` | none | Invitation detail. |
| `POST` | `/api/tenant/invitations/{invitation_id}/resend` | none | Updated invitation. |
| `DELETE` | `/api/tenant/invitations/{invitation_id}` | none | `204`. |
| `POST` | `/api/invitations/{token}/accept` | `AcceptInvitationRequest` | Acceptance payload. |

```ts
type InviteMemberRequest = {
  email: string;
  role: "admin" | "member" | "viewer";
};

type UpdateMemberRoleRequest = {
  role: "owner" | "admin" | "member" | "viewer";
};

type TransferOwnershipRequest = {
  target_user_id: string;
};
```

## Audit Logs And Notifications

| Method | Path | Query/Request | Response |
| --- | --- | --- | --- |
| `GET` | `/api/audit-logs` | `user_id`, `action`, `resource_type`, `resource_id`, `result`, `created_from`, `created_to`, `search`, `limit`, `offset` | `Page<AuditLog>`. |
| `GET` | `/api/audit-logs/{audit_id}` | none | Audit log detail. |
| `GET` | `/api/audit-logs/export` | tenant-scoped audit filters | `text/csv`. |
| `GET` | `/api/notifications` | `unread_only`, `type`, `severity`, `limit`, `offset` | Notification page with unread count. |
| `POST` | `/api/notifications/{notification_id}/read` | none | Updated notification. |
| `POST` | `/api/notifications/read-all` | none | `{ updated, unread_count }` or equivalent payload. |
| `DELETE` | `/api/notifications/{notification_id}` | none | `204`. |
| `POST` | `/api/notifications/clear-read` | none | `{ deleted, unread_count }`. |

Audit logs are append-only. No update or delete endpoints exist.

## System Admin

System admin endpoints require `user.is_system_admin`.

| Method | Path | Request | Response |
| --- | --- | --- | --- |
| `GET` | `/api/admin/tenants` | none | Tenant list. |
| `GET` | `/api/admin/tenants/{tenant_id}` | none | Tenant detail. |
| `PATCH` | `/api/admin/tenants/{tenant_id}/subscription` | `UpdateSubscriptionRequest` | Updated subscription/tenant state. |
| `GET` | `/api/admin/plans` | none | `Plan[]`. |
| `POST` | `/api/admin/plans` | `CreatePlanRequest` | `Plan`. |
| `PATCH` | `/api/admin/plans/{plan_id}` | `UpdatePlanRequest` | `Plan`. |
| `GET` | `/api/admin/system/usage` | none | System usage payload. |
| `GET` | `/api/admin/users` | `limit`, `offset` | `Page<User>`. |
| `GET` | `/api/admin/users/{user_id}` | none | User detail without password hash. |
| `GET` | `/api/admin/system/health` | none | API, PostgreSQL, worker, scheduler, queue, runtime health. |
| `GET` | `/api/admin/system/runtimes` | `limit`, `offset` | Runtime page without profile path or CDP URL. |
| `GET` | `/api/admin/system/queue` | `limit`, `offset` | Queue item page. |
| `GET` | `/api/admin/audit-logs` | `limit`, `offset` | System audit page. |

## Database Migration

Revision `010_frontend_crud_support` adds Campaign UI fields, Lead management fields, and `lead_notes`.

Added columns:

- `campaigns.description`
- `campaigns.target_regions_json`
- `campaigns.content_types_json`
- `campaigns.content_language`
- `leads.manual_intent_level`
- `leads.assigned_user_id`
- `leads.contacted_at`
- `leads.invalid_reason`
- `leads.updated_by`

The migration intentionally contains no database foreign keys.

## Core Response Records

Most records are returned directly from storage dictionaries. Important fields:

```ts
type Campaign = {
  id: string;
  tenant_id: string;
  name: string;
  description?: string | null;
  platform_account_id: string;
  platform?: string | null;
  platform_account_name?: string | null;
  keyword_count?: number;
  lead_count?: number;
  pending_reply_count?: number;
  last_execution_at?: string | null;
  next_run_at?: string | null;
  owner_name?: string | null;
  status: string;
  target_policy: string;
  max_contents: number;
  max_comments: number;
  min_confidence: number;
  max_leads?: number | null;
  daily_limit?: number | null;
  lead_detection_mode?: "rules_only" | "rules_with_llm";
  reply_mode?: "disabled" | "manual_approval" | "automatic";
  default_reply_template_id?: string | null;
  positive_keywords_json?: string[];
  negative_keywords_json?: string[];
  excluded_authors_json?: string[];
  excluded_comment_patterns_json?: string[];
  default_whatsapp?: string | null;
  default_email?: string | null;
  default_website?: string | null;
  default_contact_text?: string | null;
  target_regions_json?: string[];
  content_types_json?: string[];
  content_language?: string;
  deleted_at?: string | null;
  created_at: string;
  updated_at: string;
};

type ReplyTemplate = {
  id: string;
  tenant_id: string;
  name: string;
  description?: string | null;
  content: string;
  platform: "facebook";
  language: "zh-CN" | "en-US";
  enabled: boolean;
  priority: number;
  is_default: boolean;
  created_by?: string | null;
  archived_at?: string | null;
  created_at: string;
  updated_at: string;
};

type ReplyCandidate = {
  id: string;
  tenant_id: string;
  campaign_id: string;
  execution_id: string;
  reply_plan_id: string;
  platform_account_id: string;
  platform: string;
  comment_id?: string | null;
  author_name?: string | null;
  comment_text?: string | null;
  source_content_url?: string | null;
  direct_comment_url?: string | null;
  matched_rule_id?: string | null;
  matched_rule_name?: string | null;
  reply_template_id?: string | null;
  rendered_reply_text?: string | null;
  status: "pending_approval" | "approved" | "blocked" | "rejected" | "cancelled" | "sent" | string;
  blocked_reason?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  rejected_by?: string | null;
  rejected_at?: string | null;
  sent_at?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
};

type ReplyPlan = {
  id: string;
  tenant_id: string;
  campaign_id: string;
  execution_id: string;
  platform_account_id: string;
  status: "pending_approval" | "approved" | "blocked" | "cancelled" | "executed" | string;
  reply_mode: "manual_approval" | "automatic" | string;
  total_candidates: number;
  approved_count: number;
  sent_count: number;
  failed_count: number;
  blocked_reason?: string | null;
  created_by?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  executed_at?: string | null;
  created_at: string;
  updated_at: string;
};
```

## Frontend Integration Checklist

- Always send only documented schema fields for strict endpoints.
- For campaign create, send `initial_keywords`; do not call keyword create separately unless user is explicitly editing keywords after campaign creation.
- For reply template content, validate the variable whitelist before submit and still handle backend 422.
- For match rules, compile/check regex before submit and still handle backend 422/400.
- For candidate reject and bulk reject, require a user-entered reason.
- Keep execute buttons disabled when settings or execution state indicates sending is disabled; backend guard remains authoritative.
- On 409, keep forms/modals open and refresh the row/list after showing the conflict.
- Prefer passing `limit` and `offset` to pageable list endpoints to get the `Page<T>` shape consistently.
