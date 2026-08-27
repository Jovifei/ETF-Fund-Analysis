#!/usr/bin/env bash
set -euo pipefail
base="${1:-http://127.0.0.1:${APP_PORT:-8080}}"
token="${PRIVATE_ACCESS_TOKEN:-}"
curl -fsS "$base/api/health" | python -m json.tool
if [[ -n "$token" ]]; then
  curl -fsS -H "Authorization: Bearer $token" "$base/api/bootstrap" >/tmp/fund_bootstrap.json
  python - <<'PY'
import json
p=json.load(open('/tmp/fund_bootstrap.json'))
print({'instrument_count':p['summary']['instrument_count'],'state_counts':p['summary']['state_counts']})
PY
else
  echo "Set PRIVATE_ACCESS_TOKEN to test protected endpoints." >&2
fi
