# SaaS production deployment

## Deployment modes

`SAAS_DEPLOYMENT_MODE` declares the production boundary:

- `windows-local`: API, Worker, Browser Runtime, and Chrome run on the same Windows host. PostgreSQL and the frontend may run in Docker.
- `control-plane-only`: API and Scheduler may run, but browser runtime operations and campaign execution return an explicit unavailable error.

Linux containers cannot reach Windows Chrome through container-local `127.0.0.1`. Do not set `windows-local` inside the Linux API container. A remote runtime agent is not implemented in this phase.

`GET /api/system/runtime-capabilities` exposes only safe capability fields. It never returns Chrome paths, profile paths, or CDP URLs.

Bootstrap credentials are used only when the database has no users. Remove `SAAS_BOOTSTRAP_ADMIN_PASSWORD` immediately after the first successful startup.

## Architecture and boundary

Nginx serves the React build and proxies `/api` to one FastAPI process. FastAPI, Scheduler, and Worker share PostgreSQL 16; Scheduler enqueues and Worker claims queue rows. Docker logging uses bounded `json-file` rotation.

The current browser implementation launches Windows Chrome and uses local CDP plus local profiles. `SAAS_RUNTIME_HOST=local` is implemented only for processes on the same host as Chrome. Inside a Linux container, `local` means container-local and never means the Windows host. `windows-agent` is a guarded future boundary: runtime control returns `501 runtime_host_not_implemented`, and no remote agent exists yet. No startup reconciliation auto-starts tenant browsers.

### Browser Runtime Deployment Boundary

The supported real-browser topology is:

- PostgreSQL, migrations, and frontend/Nginx may run in Docker.
- API, Worker, Browser Runtime, and Chrome run on the Windows host.
- Scheduler may run in Docker or on Windows only after the Windows Worker is online.
- All host processes use the same PostgreSQL database and explicit per-runtime CDP URLs.

The production Compose file is a Docker control plane, not a complete Facebook automation deployment. Its current default runtime host is `local`; inside the Linux API container that still means container-local, never the Windows host. The container Worker is behind the `future-runtime-agent` profile and Scheduler is behind the `automation` profile. Do not enable either profile as a substitute for a Windows runtime agent. For the supported host-browser arrangement, use the dedicated [Windows-local deployment guide](windows-local-deployment.md).

## Prerequisites and environment

Copy `.env.production.example` to a secret-managed `.env.production`. Set a strong PostgreSQL password, an explicit `SAAS_DATABASE_URL` using the Docker `postgres` host, and a stable `SESSION_SECRET` of at least 32 characters. Set exact `SAAS_ALLOWED_ORIGINS`; wildcard CORS with credentials is rejected. Production cookies default to `Secure=true`. Keep `SAAS_BROWSER_PROFILE_ROOT` on persistent storage, never `/tmp`.

The API uses one Uvicorn worker because login rate limiting and runtime coordination retain process-local state. PostgreSQL queue and runtime locks are database-backed, but rate limits are not shared across API replicas. Introduce a shared limiter before scaling API instances.

## First deployment

Run `docker compose --env-file .env.production -f docker-compose.saas.prod.yml config`, then build. Start PostgreSQL, wait for health, run only `saas-migrate`, and start remaining services. `scripts/deploy_saas.ps1` and `deploy/deploy_saas.sh` encode this sequence and never reset the database. Demo seed is refused unless `SAAS_ENABLE_DEMO_SEED=true`. Bootstrap credentials only create an admin when the users table is empty; the account is marked `must_change_password`.

The deployment scripts start only the Docker API control plane and frontend after migration. For a real Windows browser host, point Nginx/frontend at the host API, set `SAAS_RUNTIME_HOST=local`, and start API and Worker from the repository with the same production environment: `uvicorn src.facebook_leads.saas.api:app --host 0.0.0.0 --port 8000 --workers 1` and `py scripts/saas_worker.py`. Start Scheduler with `py scripts/saas_scheduler.py` only after the Worker is online. Worker concurrency defaults to one and shutdown signals stop new claims before exit.

## Health and operations

`/api/health` is process liveness. `/api/ready` verifies PostgreSQL and current Alembic revision. `/api/version` exposes only build metadata. Authenticated `/api/system/worker-status` and `/api/system/scheduler-status` expose bounded operational state without hostnames, arguments, paths, tokens, or CDP URLs.

Campaign schedules coalesce missed periods into at most one enqueue before calculating the next future run. Queue backpressure defaults to 50 pending tasks per tenant. A full queue retries after five minutes without recording a successful schedule run. Workers heartbeat throughout long executions. Every SaaS Campaign execution is constructed with `send_disabled=true`; deployment does not invoke reply batch scripts.

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
