# SaaS Productization

Phase 7.6 adds tenant administration, plan and quota enforcement, audit history,
notifications, and an isolated system-administration surface. It does not add a
payment provider. Subscriptions and tenant status are assigned manually.

## Plans And Subscriptions

Run the idempotent seed after migration:

```powershell
py scripts\saas_migrate.py
py scripts\saas_seed_plans.py
```

The seed creates `free`, `starter`, `pro`, `enterprise`, and `legacy`. Limits
live in `PLAN_DEFINITIONS` in `src/facebook_leads/saas/productization.py`.
`NULL` means unlimited. A subscription override wins over its plan value.
Existing tenants without a subscription are assigned `legacy`.

Monthly usage follows `current_period_start` and `current_period_end`. If either
value is absent, the service uses the current UTC calendar month. User,
platform-account, and campaign limits are current counts. Execution, token, and
lead limits are period totals calculated in the database.

Execution and token quotas block new enqueue operations with HTTP 429 and a
structured `quota_exceeded` response. Lead quota is warning-only so discovery
never drops a lead. Scheduler and multi-keyword access are plan feature flags.

## Members And Invitations

Owners and admins can list members. Admins manage member and viewer roles;
owners can also manage admins. The final owner cannot be removed or demoted.
Ownership transfer promotes the target and demotes the current owner in one
transaction.

Invitation tokens are returned once and only their SHA-256 hash is stored.
Invitations expire after seven days and cannot be accepted twice. Existing users
accept while signed in. New users provide their display name and password.
Email delivery is intentionally not required; the Members page provides a copyable
invite link.

## Audit And Notifications

Audit records are tenant scoped and visible only to owners and admins. Sensitive
keys including passwords, authorization values, cookies, API keys, raw tokens,
CDP URLs, and profile paths are redacted by `AuditService`. Proxy forwarding is
ignored unless `SAAS_TRUST_PROXY=true`.

Execution completion, partial completion, and failure create best-effort
notifications. Notification failure cannot change the execution result. Quota
warnings are emitted at 80, 90, and 100 percent and deduplicated by period,
resource, and threshold.

## System Administration

Set `SAAS_BOOTSTRAP_SYSTEM_ADMIN_EMAIL` to promote an existing user during API
startup. The account keeps the normal password and session system. System-admin
permission does not grant tenant business permissions.

The `/admin` surface lists tenant plans, usage, and health summaries. It can
assign plans and suspend or reactivate a tenant. Suspended tenants may sign in
and read history, but campaign execution, scheduling, runtime control, and
tenant writes are blocked. Runtime secrets, cookies, profile paths, and CDP
details are not exposed by admin APIs.

## Safety

Every manual, scheduled, and worker execution remains `send_disabled=true`.
Phase 7.6 does not execute Batch Plans or send Facebook replies. It does not add
Instagram, TikTok, X, or Ozon implementations.
