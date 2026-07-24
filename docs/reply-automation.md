# Reply Automation

Phase 7.7 adds user-configured reply automation without making LLM output a dependency.

## Safety Defaults

- New campaigns default to `reply_mode=manual_approval`.
- Existing campaigns are migrated to `reply_mode=disabled`.
- `SAAS_SYSTEM_SEND_ENABLED` defaults to `false`.
- Sending requires all guards to pass: system send enabled, tenant reply enabled, campaign reply mode not disabled, runtime available, and approved candidates in manual mode.
- The Windows-local Facebook acceptance flow is read-only for this phase: scan comments, create reply candidates, render templates, and create a pending approval plan. It does not send Facebook replies.

## Templates

Reply templates are tenant-owned and include:

`id`, `tenant_id`, `name`, `description`, `content`, `platform`, `language`, `enabled`, `priority`, `is_default`, `created_by`, `created_at`, `updated_at`, `archived_at`.

Allowed variables:

- `{{whatsapp}}`
- `{{email}}`
- `{{website}}`
- `{{contact}}`
- `{{campaign_name}}`
- `{{keyword}}`
- `{{author_name}}`

Unknown variables are rejected. Variables are rendered as plain text only; there is no eval, script execution, or expression language.

## Matching

Rules support:

- `contains_any`
- `contains_all`
- `exact`
- `regex`
- `author_exclude`
- `comment_language`
- `minimum_length`
- `maximum_length`

Campaigns also carry positive keywords, negative keywords, excluded authors, and excluded comment patterns.

Evaluation order:

1. Dedupe
2. Self-account or author exclusion
3. Already-replied exclusion
4. Negative rules
5. Positive rules
6. Template selection
7. Candidate creation

Template selection priority:

1. Rule template
2. Campaign default template
3. Tenant default template

If no template is available, the candidate is blocked with `blocked_reason=no_template`.

## Workflow

The worker reuses the existing read-only Facebook scan. After a completed execution, it reads scan artifacts and creates a Reply Plan plus Reply Candidates. Manual mode creates `pending_approval` plans and candidates. Automatic mode still passes through safety guards and is blocked while `SAAS_SYSTEM_SEND_ENABLED=false`.

The frontend splits reply automation into:

- Reply Templates
- Matching Rules
- Reply Tasks
- Reply Records

The dashboard shows pending replies, today's replied count, today's failures, and a friendly disabled-send message.
