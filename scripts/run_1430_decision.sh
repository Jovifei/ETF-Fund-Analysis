#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${ETF_DECISION_PROJECT_DIR:-/opt/china-fund-decision}"
LOCK_FILE="${ETF_1430_LOCK_FILE:-/tmp/etf-1430-decision.lock}"
cd "$PROJECT_DIR"

run_report() {
  if command -v docker >/dev/null 2>&1 && docker compose ps api --status running 2>/dev/null | grep -q api; then
    docker compose exec -T api python scripts/generate_1430_decision.py
  else
    python scripts/generate_1430_decision.py
  fi
}

if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK_FILE"
  flock -n 9 || { echo "ETF 14:30 task already running"; exit 0; }
fi

run_report
