param(
  [string]$EnvFile = ".env.production",
  [switch]$IncludeBrowserRuntime
)
$ErrorActionPreference = "Stop"
$compose = "docker-compose.saas.prod.yml"
git pull --ff-only
$env:GIT_COMMIT = (git rev-parse --short HEAD).Trim()
$env:BUILD_TIME = [DateTime]::UtcNow.ToString("o")
$env:SAAS_API_IMAGE_TAG = $env:GIT_COMMIT
$env:SAAS_WORKER_IMAGE_TAG = $env:GIT_COMMIT
$env:SAAS_FRONTEND_IMAGE_TAG = $env:GIT_COMMIT
if ($IncludeBrowserRuntime) {
  $env:SAAS_BROWSER_RUNTIME_IMAGE_TAG = "browser-runtime-$($env:GIT_COMMIT)"
  docker compose --env-file $EnvFile -f $compose build saas-api saas-worker saas-browser-runtime frontend
} else {
  docker compose --env-file $EnvFile -f $compose build saas-api saas-worker frontend
}
docker compose --env-file $EnvFile -f $compose run --rm saas-migrate
docker compose --env-file $EnvFile -f $compose up -d --no-deps saas-api saas-worker frontend
if ($IncludeBrowserRuntime) {
  docker compose --env-file $EnvFile -f $compose up -d --no-deps saas-browser-runtime
}
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/api/health | Out-Null
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/api/ready | Out-Null
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/api/version | Out-Null
