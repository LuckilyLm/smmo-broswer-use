# Full CRUD Remediation Audit

Date: 2026-07-27

Scope: SaaS dashboard and matching backend APIs. This is a living audit for the full-site CRUD usability remediation. It is not a completion report.

## Confirmed System Gaps

| Area | Current Evidence | Required Remediation |
| --- | --- | --- |
| Frontend providers | Auth/session, workspace switching, route permission checks, request feedback, and global loading are still mostly implemented inside `App.tsx` and individual pages. | Split into `AuthProvider`, `WorkspaceProvider`, `PermissionProvider`, `GlobalRequestProvider`, `RequireAuth`, `RequirePermission`, and shared initialization states. |
| API client | `web/saas-dashboard/src/api.ts` only maps basic non-OK responses and dispatches a 401 event. | Add timeout, abort support, non-JSON handling, 401 single-flight session expiry, 403/404/409/422/429/500 mapping, field errors, and shared request/action integration. |
| Action loading | Many pages call `apiPost`, `apiPatch`, or `apiDelete` directly from button handlers. | Add `useAsyncAction` with independent action keys and use it for row-level edit/delete/toggle/runtime/approval/retry actions. |
| Forms | Several forms close on generic success and do not consistently map 422 field errors. | Standardize submit loading, failed-submit retention, field mapping, dirty prompt, and success-refresh behavior. |
| Lists | Most lists use fixed `limit=100` or `limit=200` and local table rendering. | Standardize search, filters, pagination, refresh loading, empty state, error state, sorting, and column controls. |
| Permissions | Route hiding exists for manager/system-admin pages, but write buttons are still mostly page-local and role checks are incomplete. | Centralize permission checks and hide or disable forbidden write actions before backend rejection. |
| Workspace isolation | Workspace switching refreshes `me` and navigates to dashboard, but resource cache cancellation and old-tenant flash prevention are not centralized. | Persist last workspace, validate membership after login, cancel old requests, and clear per-workspace resources on switch/logout. |
| Database foreign keys | SQLAlchemy metadata previously contained 63 FK entries; migrations 001-008 still create database FKs. | Metadata now has FK count 0; Alembic 009 removes database FK constraints at head. Continue adding service-layer association validation and delete policies. |

## Module CRUD Baseline

| Page | Create | View | Edit | Delete/Archive | Enable/Disable | Search/Filter/Page | Row Loading | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Dashboard | N/A | Partial | N/A | N/A | N/A | Missing | Partial | Needs all-card navigation and per-workspace refresh guarantees. |
| Platform Accounts | Partial | Partial | Missing edit | Missing delete/archive UI | Partial runtime actions | Missing | Partial | Runtime/status actions exist but need confirmations, disable reasons, and edit/delete flows. |
| Campaigns | Partial | Missing detail | Partial | Partial | Partial | Missing | Partial | Campaign + initial Keywords creation is now backend-transactional and the frontend no longer sends helper fields to the strict schema. Still needs detail, copy, relationship navigation, and richer list controls. |
| Keywords | Improved | List only | Improved | Improved | Improved | Improved local controls | Improved | Batch create, edit, delete confirm, enable/disable row loading, search, campaign filter, status filter, and transactional backend creation are implemented. Still needs server-side pagination and full manual acceptance. |
| Leads | Missing write actions | Partial drawer | Missing | Missing invalid/archive | Missing status actions | Missing | Missing | Needs status, intent, notes, assignment, batch ops, and full timeline. |
| Reply Templates | Improved | Preview/detail partial | Improved | Improved archive | Improved | Improved local controls | Improved | Create/edit/copy/archive, enable/disable, set default, search/platform/language/status filters, variable insertion, live preview, frontend unknown-variable rejection, strict backend schemas, and row loading are implemented. Still needs server-side pagination, full impact counts, and manual browser acceptance. |
| Matching Rules | Improved | Test/detail partial | Improved | Improved archive | Improved | Improved local controls | Improved | Create/edit/archive, enable/disable, copy, priority, campaign/template/status/search filters, interactive test modal, frontend regex validation, backend strict schemas, service regex validation, and selected-template test output are implemented. Still needs server-side pagination and full manual browser acceptance. |
| Reply Tasks | Backend improved | Partial | Backend content edit guarded | Backend candidate cancel added | Backend approval improved | Missing frontend filters | Partial | Backend now requires explicit reject reason, supports candidate cancel, bulk approve, bulk reject, strict candidate content payload, and state guards for locked candidate content and plan cancel. Frontend remediation remains pending per latest user direction. |
| Reply Records | Read only partial | Missing full detail | N/A | N/A | N/A | Missing | N/A | Needs filters, export, candidate/plan/comment links, validation details. |
| Execution Records | Partial | Partial drawer | N/A | Cancel partial | Retry missing | Missing | Missing | Needs retry, queued cancel, request cancel, artifacts/log/screenshot/token views. |
| Token Usage | Summary partial | Details partial | N/A | N/A | N/A | Missing | N/A | Needs time ranges, model/campaign grouping, export, details filters. |
| Plans/Usage | Read partial | Partial | Admin partial | N/A | Feature view partial | Missing | Missing | Needs quota-driven UI disabling and admin modification confirmations. |
| Members | Partial invite | Partial | Partial role | Partial remove/revoke | N/A | Missing | Missing | Needs resend invite, transfer/role/remove confirmations, details, filters. |
| Audit Logs | Read partial | Partial drawer | N/A | N/A | N/A | Missing | N/A | Needs filters, search, export, metadata detail. |
| Notifications | Partial | Partial drawer | N/A | Missing delete/cleanup | Read partial | Partial | Missing | Needs delete, cleanup read, target navigation, row loading. |
| Settings | Partial | Form | Partial | N/A | Reply switch partial | N/A | Submit partial | Needs dirty prompt, field errors, session/security/UI preferences. |
| System Admin | Partial | Partial | Partial | Suspend partial | Feature/plan partial | Missing | Missing | Needs system-admin-only confirmation flows and user/audit lookup. |

## Verification Snapshot

| Check | Result |
| --- | --- |
| SQLAlchemy metadata FK count | 0 |
| SQLite Alembic head FK count | 0 |
| New no-FK tests | `3 passed` |
| Session endpoint tests | `9 passed` |
| Frontend production build | Passed |
| Campaign transaction tests | Passed |
| Keywords interaction tests | Passed |
| Reply Templates backend tests | `12 passed` |
| Reply Templates interaction tests | `3 passed` |
| Matching Rules backend tests | `14 passed` |
| Matching Rules interaction tests | `3 passed` |
| Reply Tasks backend tests | `16 passed` |

## Remaining Acceptance Work

The objective is not complete. Remaining work must continue through shared frontend infrastructure, page-by-page CRUD closure, backend association validation/delete policies, complete interaction tests, and manual browser acceptance for every menu.
