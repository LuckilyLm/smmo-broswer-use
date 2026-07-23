# SaaS production deployment

## Architecture and boundary

Nginx serves the React build and proxies `/api` to one FastAPI process. FastAPI, Scheduler, and Worker share PostgreSQL 16; Scheduler enqueues and Worker claims queue rows. Docker logging uses bounded `json-file` rotation.

The current browser implementation launches Windows Chrome and uses local CDP plus local profiles. `SAAS_RUNTIME_HOST=local` is implemented; `windows-agent` is reserved configuration, not a remote-agent implementation. On Windows, run API and Worker on the host when they must launch or reach Windows Chrome. PostgreSQL, Migration, Scheduler, and Nginx can remain in Docker. Do not pretend a Linux container can operate host Windows Chrome. No startup reconciliation auto-starts tenant browsers.

## Prerequisites and environment

Copy `.env.production.example` to a secret-managed `.env.production`. Set a strong PostgreSQL password and a stable `SESSION_SECRET` of at least 32 characters. Set exact `SAAS_ALLOWED_ORIGINS`; wildcard CORS with credentials is rejected. Production cookies default to `Secure=true`. Keep `SAAS_BROWSER_PROFILE_ROOT` on persistent storage, never `/tmp`.

The API uses one Uvicorn worker because login rate limiting and runtime coordination retain process-local state. PostgreSQL queue and runtime locks are database-backed, but rate limits are not shared across API replicas. Introduce a shared limiter before scaling API instances.

## First deployment

Run `docker compose --env-file .env.production -f docker-compose.saas.prod.yml config`, then build. Start PostgreSQL, wait for health, run only `saas-migrate`, and start remaining services. `scripts/deploy_saas.ps1` and `deploy/deploy_saas.sh` encode this sequence and never reset the database. Demo seed is refused unless `SAAS_ENABLE_DEMO_SEED=true`. Bootstrap credentials only create an admin when the users table is empty; the account is marked `must_change_password`.

For a Windows browser host, start the API and Worker from the repository with the same production environment: `uvicorn src.facebook_leads.saas.api:app --host 0.0.0.0 --port 8000 --workers 1` and `py scripts/saas_worker.py`. Start Scheduler with `python scripts/saas_scheduler.py`. Worker concurrency defaults to one and shutdown signals stop new claims before exit.

## Health and operations

`/api/health` is process liveness. `/api/ready` verifies PostgreSQL and current Alembic revision. `/api/version` exposes only build metadata. Authenticated `/api/system/worker-status` and `/api/system/scheduler-status` expose bounded operational state without hostnames, arguments, paths, tokens, or CDP URLs.

Campaign schedules coalesce missed periods into at most one enqueue before calculating the next future run. Queue backpressure defaults to 50 pending tasks per tenant. Every SaaS Campaign execution is constructed with `send_disabled=true`; deployment does not invoke reply batch scripts.

## Logs and retention

Application logging is structured stdout with timestamp, level, service, tenant, campaign, execution, runtime, and message fields. Never log cookies, tokens, passwords, CDP WebSocket URLs, or full profile paths. Compose caps each service log at 50 MB with 10 files.

Execution retention is configuration-only in this phase and never deletes Leads. Artifact paths are tenant/execution scoped under `artifacts/saas/tenants/<tenant>/executions/<execution>`. Preview cleanup with `py scripts/saas_cleanup_artifacts.py --root artifacts/saas --retention-days 30`; deletion requires explicit `--execute`.

## Backup and restore

Run `py scripts/saas_backup_postgres.py`; credentials come from `DATABASE_URL` or PostgreSQL environment, not the script. Follow `scripts/saas_restore_postgres.md` for restore. To back up a Chrome profile, stop that runtime, copy its tenant-owned profile directory, and then restart it. Do not copy a live Chrome profile.

## Upgrade and rollback

Before deployment, record the Git commit, image tags, and a verified PostgreSQL backup. Images use `saas-api:<commit>` and `saas-frontend:<commit>`. Upgrade by building the new tags, running Migration once, and starting services. Roll back by starting prior image tags only after checking migration compatibility. Code rollback is not database downgrade; automatic `alembic downgrade` is prohibited.

## Stop, uninstall, and troubleshooting

Stop services with `docker compose --env-file .env.production -f docker-compose.saas.prod.yml down`. Do not add `-v`, because that deletes database storage. Complete uninstall uses `docker compose ... down -v` and separately removes browser profiles, artifacts, and backups only after explicit human confirmation.

If readiness fails, inspect Migration and PostgreSQL health. If Worker is offline, verify its heartbeat and database URL. If browser connection fails, verify the process is running on the Windows host, the persisted profile root is correct, and CDP is reachable. Frontend route refreshes are handled by Nginx `try_files`.
