#!/usr/bin/env sh
set -eu
ENV_FILE="${1:-.env.production}"
INCLUDE_BROWSER_RUNTIME="${INCLUDE_BROWSER_RUNTIME:-false}"
COMPOSE="docker-compose.saas.prod.yml"
git pull --ff-only
export GIT_COMMIT="$(git rev-parse --short HEAD)"
export BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
export SAAS_API_IMAGE_TAG="$GIT_COMMIT"
export SAAS_WORKER_IMAGE_TAG="$GIT_COMMIT"
export SAAS_FRONTEND_IMAGE_TAG="$GIT_COMMIT"
if [ "$INCLUDE_BROWSER_RUNTIME" = "true" ]; then
  export SAAS_BROWSER_RUNTIME_IMAGE_TAG="browser-runtime-$GIT_COMMIT"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE" build saas-api saas-worker saas-browser-runtime frontend
else
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE" build saas-api saas-worker frontend
fi
docker compose --env-file "$ENV_FILE" -f "$COMPOSE" run --rm saas-migrate
docker compose --env-file "$ENV_FILE" -f "$COMPOSE" up -d --no-deps saas-api saas-worker frontend
if [ "$INCLUDE_BROWSER_RUNTIME" = "true" ]; then
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE" up -d --no-deps saas-browser-runtime
fi
curl --fail http://127.0.0.1:8080/api/health
curl --fail http://127.0.0.1:8080/api/ready
curl --fail http://127.0.0.1:8080/api/version
