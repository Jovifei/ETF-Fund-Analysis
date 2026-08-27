#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
stamp="$(date +%Y%m%d_%H%M%S)"
file="backups/fund_decision_${stamp}.sql.gz"
docker compose exec -T db sh -c 'pg_dump --clean --if-exists --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip -9 > "$file"
sha256sum "$file" > "${file}.sha256"
retention="${BACKUP_RETENTION_DAYS:-30}"
find backups -type f -name 'fund_decision_*.sql.gz' -mtime +"$retention" -delete
find backups -type f -name 'fund_decision_*.sha256' -mtime +"$retention" -delete
echo "$file"
