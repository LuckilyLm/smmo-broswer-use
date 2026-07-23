#!/usr/bin/env sh
set -eu
ENV_FILE="${1:-.env.production}"
COMPOSE="docker-compose.saas.prod.yml"
git pull --ff-only
export GIT_COMMIT="$(git rev-parse --short HEAD)"
export BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE" build
docker compose --env-file "$ENV_FILE" -f "$COMPOSE" run --rm saas-migrate
docker compose --env-file "$ENV_FILE" -f "$COMPOSE" up -d --no-deps saas-api saas-worker saas-scheduler frontend
curl --fail http://127.0.0.1:8080/api/health
curl --fail http://127.0.0.1:8080/api/ready
curl --fail http://127.0.0.1:8080/api/version
