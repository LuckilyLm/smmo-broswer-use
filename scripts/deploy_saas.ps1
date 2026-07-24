param([string]$EnvFile = ".env.production")
$ErrorActionPreference = "Stop"
$compose = "docker-compose.saas.prod.yml"
git pull --ff-only
$env:GIT_COMMIT = (git rev-parse --short HEAD).Trim()
$env:BUILD_TIME = [DateTime]::UtcNow.ToString("o")
docker compose --env-file $EnvFile -f $compose build
docker compose --env-file $EnvFile -f $compose run --rm saas-migrate
docker compose --env-file $EnvFile -f $compose up -d --no-deps saas-api frontend
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/api/health | Out-Null
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/api/ready | Out-Null
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/api/version | Out-Null
