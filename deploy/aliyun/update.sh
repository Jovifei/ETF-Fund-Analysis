#!/usr/bin/env bash
set -euo pipefail
ROOT="${1:-/opt/china-fund-decision}"
cd "$ROOT"
[[ -f .env ]] || { echo "Missing $ROOT/.env" >&2; exit 2; }
set -a
# shellcheck disable=SC1091
source .env
set +a
./scripts/backup_postgres.sh
if [[ -d .git ]]; then git pull --ff-only; fi
docker compose build --pull
docker compose up -d --remove-orphans
curl -fsS "http://127.0.0.1:${APP_PORT:-8080}/api/health" | jq .
