#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then echo "usage: $0 backups/file.sql.gz" >&2; exit 2; fi
cd "$(dirname "$0")/.."
file="$1"
[[ -f "$file" ]] || { echo "not found: $file" >&2; exit 2; }
echo "This will overwrite data in the configured PostgreSQL database. Type RESTORE to continue:"
read -r confirm
[[ "$confirm" == RESTORE ]] || exit 1
gzip -dc "$file" | docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
