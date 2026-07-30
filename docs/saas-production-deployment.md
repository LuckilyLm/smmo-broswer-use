# SaaS production deployment

## Deployment mode

`SAAS_DEPLOYMENT_MODE` declares the production boundary:

- `browser-use`: API, Worker, Browser Runtime, Chromium, PostgreSQL, and the frontend run in the Linux Docker stack.
- `control-plane-only`: API and Scheduler may run, but browser runtime operations and campaign execution return an explicit unavailable error.

`GET /api/system/runtime-capabilities` exposes only safe capability fields. It never returns browser executable paths, profile paths, or CDP URLs.

Bootstrap credentials are used only when the database has no users. Remove `SAAS_BOOTSTRAP_ADMIN_PASSWORD` immediately after the first successful startup.

## Architecture

Nginx serves the React build and proxies `/api` to one FastAPI process. FastAPI, Scheduler, Worker, and Browser Runtime share PostgreSQL. Browser automation runs inside the Linux API/Worker containers through browser-use and container-local Chromium. Docker logging uses bounded `json-file` rotation.

The browser profile root must be persistent storage, normally `/data/browser_profiles`. Each platform account owns its own profile directory and CDP port. Do not place profiles under `/tmp`.

## Prerequisites and environment

Copy `.env.production.example` to a secret-managed `.env.production`. Set a strong PostgreSQL password, an explicit `SAAS_DATABASE_URL` using the Docker `postgres` host, and a stable `SESSION_SECRET` of at least 32 characters. Set exact `SAAS_ALLOWED_ORIGINS`; wildcard CORS with credentials is rejected. Production cookies default to `Secure=true`.

The API uses one Uvicorn worker because login rate limiting and runtime coordination retain process-local state. PostgreSQL queue and runtime locks are database-backed, but rate limits are not shared across API replicas. Introduce a shared limiter before scaling API instances.

## LLM and artifact storage

Campaigns use rules-only detection unless the campaign has `llm_enabled=true` and `lead_detection_mode=rules_with_llm`. The SaaS backend requires all of the following before an LLM-enabled execution can start:

- `SAAS_LLM_ENDPOINT`: OpenAI-compatible base URL, for example `https://api.openai.com/v1`.
- `OPENAI_API_KEY`: API key.
- `SAAS_LLM_MODEL`: model name, also exported to the Facebook leads runner as `FACEBOOK_LEADS_LLM_MODEL`.

For remote MinIO or S3-compatible artifact storage, set:

- `SAAS_ARTIFACT_S3_ENABLED=true`
- `SAAS_ARTIFACT_S3_ENDPOINT`: the external S3/MinIO endpoint
- `SAAS_ARTIFACT_S3_ACCESS_KEY`
- `SAAS_ARTIFACT_S3_SECRET_KEY`
- `SAAS_ARTIFACT_S3_BUCKET`
- `SAAS_ARTIFACT_S3_REGION=us-east-1`
- `SAAS_ARTIFACT_S3_PREFIX=saas-artifacts`
- `SAAS_ARTIFACT_S3_PUBLIC_BASE_URL` when downloads should use a CDN or public gateway
- `SAAS_ARTIFACT_S3_SECURE=true` for HTTPS endpoints, `false` only for HTTP endpoints

Each completed execution writes `execution_report.html` and `execution_report.json` at the execution root. When object storage is enabled, the backend uploads the unified report and raw artifacts, then writes `artifact_manifest.json`. The execution artifact API includes `external_url` for uploaded files.

## First deployment

Run `docker compose --env-file .env.production -f docker-compose.saas.prod.yml config`, then build. Start PostgreSQL, wait for health, run only `saas-migrate`, and start remaining services. `deploy/deploy_saas.sh` encodes this sequence and never resets the database. Demo seed is refused unless `SAAS_ENABLE_DEMO_SEED=true`. Bootstrap credentials only create an admin when the users table is empty; the account is marked `must_change_password`.

## Health and operations

`/api/health` is process liveness. `/api/ready` verifies PostgreSQL and current Alembic revision. `/api/version` exposes only build metadata. Authenticated `/api/system/worker-status` and `/api/system/scheduler-status` expose bounded operational state without hostnames, arguments, paths, tokens, or CDP URLs.

Campaign schedules coalesce missed periods into at most one enqueue before calculating the next future run. Queue backpressure defaults to 50 pending tasks per tenant. A full queue retries after five minutes without recording a successful schedule run. Workers heartbeat throughout long executions. Every SaaS Campaign execution is constructed with `send_disabled=true`; deployment does not invoke reply batch scripts.

## Logs and retention

Application logging is structured stdout with timestamp, level, service, tenant, campaign, execution, runtime, and message fields. Never log cookies, tokens, passwords, CDP WebSocket URLs, or full profile paths. Compose caps each service log at 50 MB with 10 files.

Execution retention is configuration-only in this phase and never deletes Leads. Artifact paths are tenant/execution scoped under `artifacts/saas/tenants/<tenant>/executions/<execution>`. The Docker deployment mounts this path through `saas_artifacts:/app/artifacts/saas`. Preview cleanup with `py scripts/saas_cleanup_artifacts.py --root artifacts/saas --retention-days 30`; deletion requires explicit `--execute`.

## Backup and restore

Run `py scripts/saas_backup_postgres.py`; credentials come from `DATABASE_URL` or PostgreSQL environment, not the script. Follow `scripts/saas_restore_postgres.md` for restore. To back up a browser profile, stop that runtime, copy its tenant-owned profile directory, and then restart it. Do not copy a live profile.

## Upgrade and rollback

Before deployment, record the Git commit, image tags, and a verified PostgreSQL backup. Images use separate tags for `saas-api`, `saas-worker`, `saas-frontend`, and `saas-browser-runtime`. Normal backend/frontend upgrades must build and restart only `saas-api`, `saas-worker`, and `frontend` with `--no-deps`; do not rebuild, retag, or restart `saas-browser-runtime`, because that container owns the live Chromium process and noVNC login session. Use `scripts/deploy_saas.ps1` or `deploy/deploy_saas.sh` for this path.

Only update `saas-browser-runtime` when the browser runtime code, Chromium launch behavior, noVNC, or profile handling changes. On PowerShell, pass `-IncludeBrowserRuntime`; on shell, set `INCLUDE_BROWSER_RUNTIME=true`. This is expected to restart the browser container and may require re-login. Roll back by starting prior image tags only after checking migration compatibility. Code rollback is not database downgrade; automatic `alembic downgrade` is prohibited.

## Stop, uninstall, and troubleshooting

Stop services with `docker compose --env-file .env.production -f docker-compose.saas.prod.yml down`. Do not add `-v`, because that deletes database storage. Complete uninstall uses `docker compose ... down -v` and separately removes browser profiles, artifacts, and backups only after explicit human confirmation.

If readiness fails, inspect Migration and PostgreSQL health. If Worker is offline, verify its heartbeat and database URL. If browser connection fails, verify Xvfb/noVNC processes, the persisted profile root, and the account CDP port. Frontend route refreshes are handled by Nginx `try_files`.
