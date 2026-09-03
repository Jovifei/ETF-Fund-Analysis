#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT="${1:-/opt/china-fund-decision}"
cd "$ROOT"
[[ -f .env ]] || { echo "Missing $ROOT/.env; copy deploy/.env.production.example and fill secrets." >&2; exit 2; }
set -a
# shellcheck disable=SC1091
source .env
set +a
mkdir -p reports backups
chmod 600 .env
chmod 700 reports backups
chown -R 10001:10001 reports backups

docker compose config >/dev/null
docker compose build --pull
docker compose up -d db api
healthy=false
for _ in {1..40}; do
  if curl -fsS "http://127.0.0.1:${APP_PORT:-8080}/api/health" >/dev/null; then healthy=true; break; fi
  sleep 3
done
[[ "$healthy" == true ]] || { docker compose logs --tail=120 api; echo "API health check timed out" >&2; exit 3; }

docker compose run --rm api fund-decision run-task sync_instruments
docker compose run --rm api python scripts/provider_smoke.py
# Historical data can be expensive; operators may change 900 to a smaller first pass.
docker compose run --rm api fund-decision bootstrap --lookback-days 900

if [[ "${SCHEDULER_ENABLED:-true}" == "true" ]]; then
  docker compose up -d scheduler
else
  echo "Scheduler remains disabled; set SCHEDULER_ENABLED=true after data validation."
fi
docker compose ps
curl -fsS "http://127.0.0.1:${APP_PORT:-8080}/api/health" | jq .
