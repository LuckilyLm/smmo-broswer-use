# Windows-local SaaS deployment

## Purpose and boundary

This is the supported real-browser topology for the SaaS Facebook workflow:

- Docker runs PostgreSQL 16, the migration job, and the Nginx-served frontend.
- The Windows host runs the FastAPI API, Worker, Browser Runtime, Chrome, and the tenant-owned Chrome profiles.
- The frontend proxies `/api` to `http://host.docker.internal:8000`; it does not run the API in Docker.

This is not a container-only browser deployment. `127.0.0.1` inside a Linux container is that container, not Windows Chrome. The API and Worker must use `SAAS_DEPLOYMENT_MODE=windows-local` and `SAAS_RUNTIME_HOST=local` on the Windows host. The `windows-agent` runtime host is not implemented.

In contrast, **control-plane-only** is for Docker API/Scheduler use without a local Windows browser runtime. It can serve non-browser control-plane operations, but browser controls and campaign execution are explicitly unavailable. Do not treat it as an automation deployment.

## Prerequisites

- Docker Desktop with Docker Compose.
- Windows Python with the repository's SaaS dependencies installed.
- Google Chrome installed at the exact `SAAS_CHROME_EXECUTABLE` path.
- A persistent, tenant-owned `SAAS_BROWSER_PROFILE_ROOT`; do not use a temporary directory and do not reuse a personal Chrome profile.
- A PostgreSQL password, a `SESSION_SECRET` of at least 32 characters, and the required LLM configuration.

Keep the Docker PostgreSQL port bound to `127.0.0.1`; the Windows API and Worker use it through their host-side `DATABASE_URL`.

## Configure the separate Windows environment

Do not reuse the ordinary `.env` or the production Docker environment for the host processes. Create the dedicated file from the template:

```powershell
Copy-Item .env.windows-local.example .env.windows-local
```

Edit `.env.windows-local` and replace the placeholders. In addition to the template values, set the Compose interpolation values below. `SAAS_DATABASE_URL` is for containers and must use the Docker `postgres` host; the host-side `DATABASE_URL` must use `127.0.0.1`:

```dotenv
POSTGRES_DB=facebook_leads_saas
POSTGRES_USER=saas_user
POSTGRES_PASSWORD=replace-with-a-strong-password
SAAS_DATABASE_URL=postgresql+psycopg://saas_user:replace-with-a-strong-password@postgres:5432/facebook_leads_saas
DATABASE_URL=postgresql+psycopg://saas_user:replace-with-a-strong-password@127.0.0.1:5432/facebook_leads_saas
SESSION_SECRET=replace-with-a-stable-secret-of-at-least-32-characters
SAAS_ALLOWED_ORIGINS=http://127.0.0.1:8080
SAAS_CHROME_EXECUTABLE=C:\Program Files\Google\Chrome\Application\chrome.exe
SAAS_BROWSER_PROFILE_ROOT=C:\Users\<username>\AppData\Local\browser-use-webui\browser_profiles
OPENAI_API_KEY=replace-with-your-key
```

Keep the template's `SAAS_DEPLOYMENT_MODE=windows-local` and `SAAS_RUNTIME_HOST=local`. Do not commit `.env.windows-local`.

## Start the Docker control-plane services

Validate interpolation first:

```powershell
docker compose --env-file .env.windows-local -f docker-compose.saas.windows-local.yml config
```

Start PostgreSQL, apply migrations once as part of the declared service graph, then start the frontend:

```powershell
docker compose --env-file .env.windows-local -f docker-compose.saas.windows-local.yml up --build -d postgres saas-migrate frontend
```

The frontend is available at `http://127.0.0.1:8080`. Its default upstream is `http://host.docker.internal:8000` (the Windows API), supplied by `SAAS_API_UPSTREAM` in the Compose file.

## Start the Windows API and Worker

In PowerShell, start API and Worker with the supplied launchers:

```powershell
.\scripts\start_saas_api_windows.ps1 -EnvFile .env.windows-local
.\scripts\start_saas_worker_windows.ps1 -EnvFile .env.windows-local
```

The launchers load the dedicated environment, require a reachable database and current Alembic schema, validate the Chrome executable, and run one API worker. Alternatively, use the combined launcher after the frontend has started:

```powershell
.\scripts\start_saas_windows.ps1 -EnvFile .env.windows-local
```

It opens API and Worker in separate PowerShell windows and reports host health, readiness, PostgreSQL reachability, and whether the worker process remains running. Add `-WithScheduler` only when schedules are needed:

```powershell
.\scripts\start_saas_windows.ps1 -EnvFile .env.windows-local -WithScheduler
```

The Scheduler is optional for manually started campaigns. Start it only after the Worker is online; it may also be launched separately with `start_saas_scheduler_windows.ps1`.

The API launcher binds Uvicorn to `0.0.0.0:8000` so the Docker frontend can reach it through `host.docker.internal:8000`. Keep host firewall exposure restricted to the local machine or trusted networks.

## Validate services and capabilities

Check unauthenticated liveness, readiness, and build metadata from the Windows host:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/ready
Invoke-RestMethod http://127.0.0.1:8000/api/version
```

`/api/health` only proves the process is alive. `/api/ready` also verifies PostgreSQL connectivity and the current Alembic revision. `/api/version` reports build metadata.

After signing in, verify the authenticated operational endpoints:

- `GET /api/system/runtime-capabilities` confirms that a local Windows runtime is available without exposing Chrome paths, profile paths, or CDP URLs.
- `GET /api/system/worker-status` confirms an online Worker and its latest heartbeat.
- `GET /api/system/scheduler-status` confirms Scheduler state when it is enabled and shows queued/running task counts.

A process window alone is not a Worker heartbeat. Use the authenticated Worker status endpoint after login.

## Connect a Platform Account and validate Chrome

1. In **Platform Accounts**, create the Facebook account record if it does not exist.
2. Select **Browser actions** > **Connect**. The system creates the account's owned profile, allocates a CDP port, and starts Chrome using that profile.
3. Complete Facebook login manually in the Chrome window, including any challenge or MFA required by Facebook.
4. Return to **Browser actions** > **Check Login**. A successful result requires both a reachable Chrome CDP endpoint and a logged-in Facebook state.

The runtime details identify the Chrome PID and CDP port. Diagnose that individual runtime from the Windows host with:

```powershell
Get-Process -Id <browser-pid>
Invoke-RestMethod http://127.0.0.1:<cdp-port>/json/version
```

`/json/version` must respond for CDP to be reachable. If it does not, check the PID, the configured Chrome executable, the selected CDP port, and local firewall or endpoint-security policy.

Treat each generated profile as persistent account state. Do not choose **Reset Profile** during normal operation: it stops the runtime and deletes that account's owned profile after an explicit `RESET PROFILE` confirmation. Preserve the profile and use **Check Login**, Restart, or Stop as appropriate.

## Capability smoke validation

Do not claim a successful campaign from deployment alone. After the API, Worker heartbeat, and Chrome login checks succeed, run one deliberately small manual campaign:

- one keyword;
- `max_contents=1`;
- `max_comments=5`.

The expected execution progression is `queued`, then `running`, then `completed` or `partial`, depending on what Facebook makes available and any per-item failures. Inspect the execution in the UI or through the executions API; this is a capability validation, not an operational-result guarantee.

Every SaaS campaign execution is created with `send_disabled=true`. It performs no reply or message actions, and this deployment path does not invoke reply-batch scripts.

## Troubleshooting and safe shutdown

| Symptom | Check |
| --- | --- |
| `config` fails or migration cannot start | Confirm `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `SAAS_DATABASE_URL`, `SESSION_SECRET`, and `SAAS_ALLOWED_ORIGINS` are populated in `.env.windows-local`. |
| `/api/ready` returns 503 | Check Docker PostgreSQL health and run the migration command; the host launchers intentionally reject a database that is not at the current Alembic revision. |
| Frontend loads but API requests fail | Confirm `SAAS_API_UPSTREAM=http://host.docker.internal:8000`, verify the Windows API is listening on `0.0.0.0:8000`, and check Windows firewall policy. |
| Worker status is offline | Verify the Worker launcher is still running, that it uses the same `.env.windows-local` and database, and then check its authenticated heartbeat endpoint. |
| Connect or Check Login fails | Confirm the Windows-local capability, Chrome executable, profile root, Chrome PID, and `http://127.0.0.1:<cdp-port>/json/version`. Complete Facebook login manually before checking again. |
| Browser controls are unavailable | Confirm the host API is in `windows-local` mode with `SAAS_RUNTIME_HOST=local`; `control-plane-only` and `windows-agent` cannot provide a Windows browser runtime. |

Stop only the Docker services with:

```powershell
docker compose --env-file .env.windows-local -f docker-compose.saas.windows-local.yml down
```

Do not add `-v`: it deletes PostgreSQL storage. Stop the API, Worker, Scheduler, and Chrome deliberately. Do not delete Chrome profiles as part of shutdown or troubleshooting.
